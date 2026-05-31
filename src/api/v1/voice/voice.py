import json
import asyncio
import time
import hashlib
import base64
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from bson import ObjectId
import openai
import logging
from datetime import datetime
from contextlib import suppress  # Added to cleanly suppress CancelledError when awaiting task cancellation
from uuid import uuid4  # NEW: for per-connection generation tokens

from ....config import settings
from ....database import get_sessions_collection, get_patients_collection, get_recordings_collection
from ....auth.dependencies import get_current_user, get_current_user_websocket
from ....models.users import User
from ....models.history import SessionStatus, TranscriptMessage, MessageSpeaker
from ....models.recordings import Recording, RecordingCreate

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

# OpenAI client
openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if hasattr(settings, 'OPENAI_API_KEY') else None
logger.info(f"OpenAI SDK version: {openai.__version__}")

# Voice mapping for patients
PATIENT_VOICE_MAP = {
    'Natalie Rosen': 'shimmer',
    'David Morales': 'ballad', 
    'Jordan Williams': 'echo',
    'Mark Reynolds': 'verse',
    'Sarah Mitchell': 'sage',
    'Jenna Thompson': 'coral'
}

class VoiceSessionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.openai_connections: Dict[str, Any] = {}
        self.session_data: Dict[str, Dict] = {}
        self.response_accumulator: Dict[str, str] = {}
        self.awaiting_response: Dict[str, bool] = {}
        self.session_generations: Dict[str, str] = {}  # NEW: track active generation per session
        self.message_sequences: Dict[str, int] = {}  # NEW: per-session message sequence counter
        self.pending_student_seq: Dict[str, int] = {}  # NEW: reserved seq for next student transcription

    # NEW: helper to get next sequence number
    def next_sequence(self, session_id: str) -> int:
        current = self.message_sequences.get(session_id, 0) + 1
        self.message_sequences[session_id] = current
        return current

    async def connect(self, websocket: WebSocket, session_id: str, session_data: Dict, patient_data: Dict):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.session_data[session_id] = {"session": session_data, "patient": patient_data}
        self.awaiting_response[session_id] = False
        self.message_sequences[session_id] = 0  # NEW: init sequence
        logger.info(f"Session {session_id} connected for patient {patient_data.get('name')}")
        logger.info(f"🔍 Session data stored with ID: {session_id}, database _id: {session_data.get('_id')}")
        
        # Update session start time to now (when voice session actually begins)
        try:
            sessions_collection = get_sessions_collection()
            current_time = datetime.utcnow()
            
            # Find and update the session with current start time
            session_doc = await self.find_session_in_db(session_id)
            if session_doc:
                await sessions_collection.update_one(
                    {"_id": session_doc["_id"]},
                    {"$set": {"start_time": current_time, "updated_at": current_time}}
                )
                logger.info(f"✅ Updated session {session_id} start time to {current_time}")
            else:
                logger.warning(f"⚠️ Could not find session {session_id} to update start time")
        except Exception as e:
            logger.error(f"❌ Failed to update session start time: {e}")

    def disconnect(self, session_id: str):
        # Remove only AFTER generation invalidated to stop stale tasks
        self.session_generations.pop(session_id, None)  # NEW
        self.active_connections.pop(session_id, None)
        if session_id in self.openai_connections:
            asyncio.create_task(self._close_openai_connection(session_id))
        self.session_data.pop(session_id, None)
        self.response_accumulator.pop(session_id, None)
        self.awaiting_response.pop(session_id, None)
        self.message_sequences.pop(session_id, None)  # NEW: cleanup
        self.pending_student_seq.pop(session_id, None)  # NEW
        logger.info(f"Session {session_id} disconnected")

    async def _close_openai_connection(self, session_id: str):
        if ws := self.openai_connections.pop(session_id, None):
            try:
                await ws.close()
            except Exception:
                pass

    async def find_session_in_db(self, session_id: str):
        """Find session in database trying different ID formats"""
        try:
            sessions_collection = get_sessions_collection()
            
            # Try ObjectId format first
            if ObjectId.is_valid(session_id):
                session = await sessions_collection.find_one({"_id": ObjectId(session_id)})
                if session:
                    logger.info(f"✅ Found session using ObjectId format")
                    return session
            
            # Try string format
            session = await sessions_collection.find_one({"_id": session_id})
            if session:
                logger.info(f"✅ Found session using string format")
                return session
            
            logger.error(f"❌ Session {session_id} not found in database")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error finding session {session_id}: {e}")
            return None

    async def send_to_client(self, session_id: str, message: dict):
        if websocket := self.active_connections.get(session_id):
            try:
                message_json = json.dumps(message)
                # Reduced logging for audio messages to improve performance
                if message.get('type') not in ['audio_response', 'response_text_delta']:
                    logger.info(f"📤 Sending message to session {session_id}: {message.get('type', 'unknown')}")
                await websocket.send_text(message_json)
                if message.get('type') not in ['audio_response', 'response_text_delta']:
                    logger.info(f"✅ Message sent successfully to session {session_id}")
            except Exception as e:
                logger.error(f"❌ Error sending message to session {session_id}: {e}")
        else:
            logger.warning(f"⚠️ No active connection found for session {session_id}")

    async def add_message_to_session(self, session_id: str, speaker: MessageSpeaker, text: str):
        try:
            sessions_collection = get_sessions_collection()
            new_message = TranscriptMessage(
                id=str(ObjectId()),
                speaker=speaker,
                text=text,
                timestamp=datetime.utcnow()
            )
            
            logger.info(f"🔍 Adding message to session {session_id} (type: {type(session_id)})")
            
            # Try both ObjectId and string formats
            session_obj_id = None
            if ObjectId.is_valid(session_id):
                session_obj_id = ObjectId(session_id)
                logger.info(f"🔍 Using ObjectId format: {session_obj_id}")
            else:
                session_obj_id = session_id
                logger.info(f"🔍 Using string format: {session_obj_id}")
            
            # First check if session exists using our helper method
            session_check = await self.find_session_in_db(session_id)
            if not session_check:
                logger.error(f"❌ Session {session_id} does not exist in database")
                return
            
            # Use the actual session ID from the database
            session_obj_id = session_check["_id"]
            
            logger.info(f"✅ Session found, current transcript length: {len(session_check.get('transcript', []))}")
            
            result = await sessions_collection.update_one(
                {"_id": session_obj_id},
                {
                    "$push": {"transcript": new_message.dict()},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ Message added to session {session_id}: {speaker} - {text[:50]}...")
                # Verify the message was added
                updated_session = await sessions_collection.find_one({"_id": session_obj_id})
                new_transcript_length = len(updated_session.get('transcript', []))
                logger.info(f"✅ Transcript now has {new_transcript_length} messages")
            else:
                logger.error(f"❌ Failed to add message to session {session_id} - no documents modified")
                logger.error(f"❌ Update result: matched={result.matched_count}, modified={result.modified_count}")
                
        except Exception as e:
            logger.error(f"❌ Error adding message to session {session_id}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    async def save_recording(self, session_id: str, session_data: Dict, patient_data: Dict, 
                           transcription: str, analysis: str = None, audio_url: str = None):
        """Save the recording, transcript, and analysis in recordings collection"""
        try:
            recordings_collection = get_recordings_collection()
            
            # Create recording using the model
            recording_create = RecordingCreate(
                session_id=session_id,
                patient_id=session_data.get("patient_id"),
                student_id=session_data.get("student_id"),
                patient_name=patient_data.get("name", "Unknown Patient"),
                audio_url=audio_url,
                transcription=transcription,
                analysis=analysis or "Analysis pending",
                session_duration=session_data.get("duration", 0),
                message_count=len(session_data.get("transcript", [])),
                session_score=session_data.get("score", 0),
                session_feedback=session_data.get("feedback", "")
            )
            
            # Convert to dict and add timestamps
            recording_doc = recording_create.dict()
            recording_doc["created_at"] = datetime.utcnow()
            recording_doc["updated_at"] = datetime.utcnow()
            
            # Insert recording document
            result = await recordings_collection.insert_one(recording_doc)
            logger.info(f"✅ Recording saved for session {session_id} with ID: {result.inserted_id}")
            
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"❌ Failed to save recording for session {session_id}: {e}")
            return None

    async def get_session_transcript(self, session_id: str) -> str:
        """Get combined transcript text from session"""
        try:
            sessions_collection = get_sessions_collection()
            
            # Use the helper method to find the session
            session_doc = await self.find_session_in_db(session_id)
            
            if not session_doc:
                logger.warning(f"⚠️ Session {session_id} not found for transcript retrieval")
                return ""
            
            transcript_messages = session_doc.get("transcript", [])
            logger.info(f"📊 Retrieved {len(transcript_messages)} transcript messages for session {session_id}")
            
            if not transcript_messages:
                logger.warning(f"⚠️ No transcript messages found for session {session_id}")
                return ""
            
            transcript_lines = []
            
            for i, msg in enumerate(transcript_messages):
                try:
                    speaker = "Student" if msg.get("speaker") == "student" else "Patient"
                    text = msg.get("text", "")
                    timestamp = msg.get("timestamp", datetime.utcnow())
                    
                    # Handle timestamp formatting
                    if isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        except:
                            timestamp = datetime.utcnow()
                    
                    # Format: [HH:MM:SS] Speaker: Text
                    time_str = timestamp.strftime("%H:%M:%S") if isinstance(timestamp, datetime) else "00:00:00"
                    transcript_lines.append(f"[{time_str}] {speaker}: {text}")
                    
                except Exception as msg_error:
                    logger.error(f"❌ Error processing message {i} in session {session_id}: {msg_error}")
                    continue
            
            transcript_text = "\n".join(transcript_lines)
            logger.info(f"✅ Generated transcript for session {session_id}: {len(transcript_text)} characters")
            return transcript_text
            
        except Exception as e:
            logger.error(f"❌ Failed to get transcript for session {session_id}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return ""

    async def generate_session_analysis(self, session_id: str, transcript: str, session_data: Dict) -> str:
        """Generate basic session analysis"""
        try:
            transcript_messages = session_data.get("transcript", [])
            student_messages = [msg for msg in transcript_messages if msg.get("speaker") == "student"]
            patient_messages = [msg for msg in transcript_messages if msg.get("speaker") == "patient"]
            
            duration_minutes = session_data.get("duration", 0) // 60
            
            analysis = f"""SESSION ANALYSIS SUMMARY
Session ID: {session_id}
Duration: {duration_minutes} minutes
Total Messages: {len(transcript_messages)}
Student Messages: {len(student_messages)}
Patient Messages: {len(patient_messages)}

CONVERSATION FLOW:
- Student initiated {len(student_messages)} interactions
- Patient provided {len(patient_messages)} responses
- Average response length: {sum(len(msg.get('text', '')) for msg in patient_messages) // max(len(patient_messages), 1)} characters

ENGAGEMENT METRICS:
- Session Score: {session_data.get('score', 0)}/100
- Communication Balance: {'Good' if len(student_messages) > 0 and len(patient_messages) > 0 else 'Needs Improvement'}
- Session Completion: {'Complete' if session_data.get('status') == 'completed' else 'Incomplete'}

RECOMMENDATIONS:
- Continue practicing active listening techniques
- Focus on open-ended questions to encourage patient engagement
- Maintain professional therapeutic boundaries
"""
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Failed to generate analysis for session {session_id}: {e}")
            return "Analysis generation failed"

    async def save_audio_file(self, session_id: str, audio_data: bytes) -> str:
        """Save audio file to GridFS (placeholder for future implementation)"""
        try:
            # TODO: Implement GridFS storage for audio files
            # from gridfs import GridFS
            # fs = GridFS(db.database)
            # file_id = fs.put(audio_data, filename=f"session_{session_id}.wav", content_type="audio/wav")
            # return str(file_id)
            
            # For now, return a placeholder
            logger.info(f"📁 Audio file storage placeholder for session {session_id} ({len(audio_data)} bytes)")
            return f"audio_placeholder_{session_id}_{int(time.time())}"
            
        except Exception as e:
            logger.error(f"❌ Failed to save audio file for session {session_id}: {e}")
            return None

manager = VoiceSessionManager()

def create_patient_system_prompt(patient: Dict) -> str:
    """Create patient system prompt with key behavioral constraints"""
    name = patient.get('name', 'Unknown Patient')
    age = patient.get('age', 'unknown')
    condition = patient.get('condition', 'general distress')
    emotional_state = patient.get('emotional_state', 'neutral').lower()
    personality = patient.get('personality', 'reserved').lower()
    presenting_problem = patient.get('presenting_problem', condition)
    dialogue_responses = patient.get('dialogue_responses', [])

    example_responses = ""
    if dialogue_responses:
        example_responses = f"""
SPEECH EXAMPLES FROM {name.upper()}:
{chr(10).join([f'"{response}"' for response in dialogue_responses[:4]])}
"""

    # Dynamic greeting responses based on emotional state and personality
    greeting_variations = {
        'anxious': ["I'm nervous", "A bit worried", "Anxious, I guess", "Not sure about this"],
        'depressed': ["Not great", "Pretty low", "Could be better", "Just tired"],
        'angry': ["I'm here", "Fine", "Whatever", "Let's get this over with"],
        'frustrated': ["Frustrated", "This is hard", "I don't know", "Annoyed"],
        'hopeful': ["Okay, I think", "Trying to be positive", "Hopeful maybe", "Ready to try"],
        'neutral': ["I'm okay", "Alright", "Fine, I guess", "Here I am"],
        'positive': ["Pretty good", "Doing alright", "Not bad", "Good, thanks"],
        'confused': ["I don't know", "Confused", "Not sure", "Everything's mixed up"],
        'overwhelmed': ["Too much going on", "Overwhelmed", "Can't handle it", "Everything's too much"]
    }
    
    # Get appropriate greetings, fallback to neutral if not found
    greetings = greeting_variations.get(emotional_state, greeting_variations['neutral'])
    
    # Adjust behavior based on personality
    personality_traits = {
        'outgoing': "- Be more talkative and expressive than usual\n- Share details more readily",
        'reserved': "- Keep responses brief and guarded\n- Take time to open up",
        'aggressive': "- Show some defensiveness or irritation\n- Be direct and blunt",
        'passive': "- Speak quietly and hesitantly\n- Defer and minimize your problems",
        'analytical': "- Think through responses carefully\n- Ask for clarification occasionally"
    }
    
    personality_behavior = personality_traits.get(personality, personality_traits['reserved'])

    return f"""You are {name}, a {age}-year-old patient seeking therapy help.

PATIENT PROFILE:
- Name: {name}
- Age: {age}
- Condition: {condition}
- Emotional State: {emotional_state}
- Personality: {personality}
- Seeking help for: {presenting_problem}

{example_responses}

CRITICAL BEHAVIOR RULES:
❌ NEVER ask questions to the therapist ("How are you?" "What do you think?")
❌ NEVER use therapeutic language ("It sounds like", "That must be", "overwhelming")
❌ NEVER give advice or be supportive to the therapist
❌ Keep responses brief (8-20 words typically)
❌ NO professional or clinical terminology

✅ REQUIRED PATIENT BEHAVIOR:
- Stay consistent with your {emotional_state} emotional state
- Match your {personality} personality style:
{personality_behavior}
- Use simple vocabulary: "I don't know", "I guess", "Maybe"
- Reference your problems: {presenting_problem}
- You need help, you don't provide it

GREETING RESPONSES: {', '.join(greetings)}

Stay in character as {name} - a patient with their own mood and personality style, reacting naturally while staying true to your profile."""

async def handle_openai_realtime(session_id: str, patient_data: Dict, generation: str):
    """Handle OpenAI Realtime API connection using the official Python SDK."""
    try:
        if manager.session_generations.get(session_id) != generation:
            logger.info(f"🛑 Aborting OpenAI init (stale generation) session={session_id}")
            return

        if not openai_client:
            logger.error("OpenAI client not initialized — check OPENAI_API_KEY")
            await manager.send_to_client(session_id, {
                "type": "error",
                "error": {"message": "OpenAI client not initialized"}
            })
            return

        patient_name = patient_data.get('name', 'Unknown')
        voice_type = PATIENT_VOICE_MAP.get(patient_name, 'marin')  # 'marin' is gpt-realtime-2 default

        if voice_type == 'marin' and patient_name:
            for mapped_name, mapped_voice in PATIENT_VOICE_MAP.items():
                if mapped_name.lower() == patient_name.lower().strip():
                    voice_type = mapped_voice
                    break

        logger.info(f"🎤 Selected voice '{voice_type}' for {patient_name}")
        system_prompt = create_patient_system_prompt(patient_data)

        async with openai_client.realtime.connect(model="gpt-realtime-2") as connection:
            if manager.session_generations.get(session_id) != generation:
                logger.info(f"🛑 Discarding SDK connection (stale generation) session={session_id}")
                return

            manager.openai_connections[session_id] = connection
            logger.info(f"OpenAI WebSocket connected for session {session_id} gen={generation}")

            # Skip session.update entirely — just log what the server sends
            logger.info(f"✅ Connected to {patient_name} — NOT sending session.update, waiting for server events")

            await manager.send_to_client(session_id, {
                "type": "connection_established",
                "message": f"Connected to {patient_name} simulation",
                "patient_name": patient_name,
                "session_id": session_id
            })

            async for event in connection:
                if session_id not in manager.active_connections:
                    logger.info(f"🛑 Client gone; stopping OpenAI stream session={session_id}")
                    break
                if manager.session_generations.get(session_id) != generation:
                    logger.info(f"🛑 Generation changed; stopping session={session_id}")
                    break

                try:
                    event_type = event.type

                if event_type == "session.updated":
                    logger.info(f"✅ Session configured for {patient_name}")
                elif event_type == "input_audio_buffer.speech_started":
                    await manager.send_to_client(session_id, {"type": "speech_started"})
                elif event_type == "input_audio_buffer.speech_stopped":
                    if session_id not in manager.pending_student_seq:
                        manager.pending_student_seq[session_id] = manager.next_sequence(session_id)
                    await manager.send_to_client(session_id, {"type": "speech_stopped"})
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcription = getattr(event, 'transcript', '').strip()
                    if transcription:
                        logger.info(f"🎤 Student: '{transcription}'")
                        reserved = manager.pending_student_seq.pop(session_id, None)
                        seq_to_use = reserved if reserved is not None else manager.next_sequence(session_id)
                        await manager.send_to_client(session_id, {
                            "type": "transcription_complete",
                            "text": transcription,
                            "speaker": "student",
                            "seq": seq_to_use
                        })
                        asyncio.create_task(manager.add_message_to_session(session_id, MessageSpeaker.STUDENT, transcription))
                elif event_type in ("response.output_audio_transcript.delta", "response.output_text.delta",
                                    "response.audio_transcript.delta"):
                    text_delta = getattr(event, 'delta', '') or ''
                    if text_delta:
                        if session_id not in manager.response_accumulator:
                            manager.response_accumulator[session_id] = ""
                        manager.response_accumulator[session_id] += text_delta
                        await manager.send_to_client(session_id, {
                            "type": "response_text_delta",
                            "delta": text_delta
                        })
                elif event_type in ("response.output_audio.delta", "response.audio.delta"):
                    if session_id not in manager.active_connections or manager.session_generations.get(session_id) != generation:
                        break
                    audio_data = getattr(event, 'delta', None) or getattr(event, 'audio', None)
                    if audio_data:
                        await manager.send_to_client(session_id, {
                            "type": "audio_response",
                            "audio": audio_data
                        })
                elif event_type == "response.done":
                    if session_id not in manager.active_connections or manager.session_generations.get(session_id) != generation:
                        break
                    await manager.send_to_client(session_id, {"type": "audio_response_complete"})
                    manager.awaiting_response[session_id] = False
                    accumulated_text = manager.response_accumulator.get(session_id, "")
                    if accumulated_text:
                        logger.info(f"🤖 Patient: '{accumulated_text[:80]}'")
                        await manager.send_to_client(session_id, {
                            "type": "patient_text_response",
                            "text": accumulated_text,
                            "speaker": "patient",
                            "seq": manager.next_sequence(session_id)
                        })
                        asyncio.create_task(manager.add_message_to_session(session_id, MessageSpeaker.PATIENT, accumulated_text))
                        manager.response_accumulator[session_id] = ""
                elif event_type == "error":
                    logger.error(f"OpenAI API error: {event}")
                    error_msg = {}
                    if hasattr(event, 'error') and event.error:
                        error_msg = {"message": str(event.error)}
                    await manager.send_to_client(session_id, {"type": "error", "error": error_msg})

                except Exception as evt_err:
                    logger.error(f"Error handling event '{event_type}': {evt_err}")

    except asyncio.CancelledError:
        logger.info(f"OpenAI task cancelled for session {session_id}")
        raise
    except Exception as e:
        logger.error(f"OpenAI connection error for session {session_id}: type={type(e).__name__} module={type(e).__module__} msg={e}")
        await manager.send_to_client(session_id, {
            "type": "error",
            "error": {"message": f"OpenAI connection failed: {str(e)}"}
        })
    finally:
        if session_id in manager.openai_connections and manager.session_generations.get(session_id) == generation:
            await manager._close_openai_connection(session_id)

@router.websocket("/realtime/{patient_id}")
async def websocket_endpoint(websocket: WebSocket, patient_id: str, token: str = Query(...)):
    """Main WebSocket endpoint for realtime voice therapy sessions"""
    session_id = None
    openai_task = None
    heartbeat_task = None
    disconnect_reason = "unknown"
    generation = uuid4().hex  # NEW: unique generation for this websocket
    
    try:
        # Authentication
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        current_user = await get_current_user_websocket(token)
        if not current_user:
            await websocket.close(code=1008, reason="Invalid token")
            return

        logger.info(f"✅ User authenticated: {current_user.email}")

        # Get collections
        sessions_collection = get_sessions_collection()
        patients_collection = get_patients_collection()

        # Find active session - try both ObjectId and string formats for patient_id
        session = None
        if ObjectId.is_valid(patient_id):
            session = await sessions_collection.find_one({
                "patient_id": ObjectId(patient_id),
                "student_id": current_user.id,
                "status": SessionStatus.ACTIVE
            })
        if not session:
            session = await sessions_collection.find_one({
                "patient_id": patient_id,
                "student_id": current_user.id,
                "status": SessionStatus.ACTIVE
            })
        
        logger.info(f"🔍 Session search for patient_id={patient_id}, student_id={current_user.id}: {'Found' if session else 'Not found'}")

        if not session:
            await websocket.close(code=1008, reason="No active session found")
            return

        # Get patient data
        patient = None
        if ObjectId.is_valid(patient_id):
            patient = await patients_collection.find_one({"_id": ObjectId(patient_id)})
        if not patient:
            patient = await patients_collection.find_one({"_id": patient_id})
        if not patient:
            await websocket.close(code=1008, reason="Patient not found")
            return

        # Use the actual database session ID
        session_id = str(session["_id"])
        # Register generation BEFORE starting OpenAI task
        manager.session_generations[session_id] = generation  # NEW
        logger.info(f"🔗 Using session ID: {session_id} (type: {type(session['_id'])}) gen={generation}")

        # Connect to session
        await manager.connect(websocket, session_id, session, patient)

        # Start OpenAI connection
        openai_task = asyncio.create_task(handle_openai_realtime(session_id, patient, generation))  # UPDATED

        # Wait for OpenAI connection
        connection_timeout = 10
        start_time = asyncio.get_event_loop().time()
        
        while session_id not in manager.openai_connections:
            await asyncio.sleep(0.1)
            if asyncio.get_event_loop().time() - start_time > connection_timeout:
                await websocket.close(code=1011, reason="Connection timeout")
                return

        logger.info(f"Ready to process audio for session {session_id}")

        # Heartbeat to keep connection alive (some proxies close idle WS)
        async def heartbeat():
            try:
                while session_id in manager.active_connections:
                    await asyncio.sleep(20)
                    if session_id in manager.active_connections:
                        await manager.send_to_client(session_id, {"type": "server_heartbeat", "ts": datetime.utcnow().isoformat()})
            except Exception as hb_err:
                logger.debug(f"Heartbeat stopped for {session_id}: {hb_err}")

        heartbeat_task = asyncio.create_task(heartbeat())

        # Main message loop
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect as wd:
                disconnect_reason = f"client_disconnect(code={wd.code})"
                raise
            except Exception as recv_err:
                logger.error(f"Receive error session {session_id}: {recv_err}")
                disconnect_reason = f"receive_error:{recv_err}"
                break

            if message.get("type") == "websocket.disconnect":
                disconnect_reason = "client_initiated"
                break

            if message.get("type") == "websocket.receive":
                # Handle binary audio data
                if message.get("bytes") is not None:
                    audio_bytes = message["bytes"]
                    conn = manager.openai_connections.get(session_id)
                    if conn:
                        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                        await conn.input_audio_buffer.append(audio=b64_audio)

                # Handle text commands
                elif message.get("text") is not None:
                    try:
                        data = json.loads(message["text"])
                        message_type = data.get("type")

                        if message_type == "audio_data":
                            audio_data = data.get("audio", "")
                            conn = manager.openai_connections.get(session_id)
                            if conn:
                                await conn.input_audio_buffer.append(audio=audio_data)

                        elif message_type == "audio_commit":
                            conn = manager.openai_connections.get(session_id)
                            if conn and not manager.awaiting_response.get(session_id, False):
                                manager.awaiting_response[session_id] = True
                                await conn.input_audio_buffer.commit()
                                await conn.response.create()

                        elif message_type == "text_message":
                            text_input = data.get("text", "").strip()
                            conn = manager.openai_connections.get(session_id)
                            if text_input and conn and not manager.awaiting_response.get(session_id, False):
                                logger.info(f"💬 Processing text message: '{text_input}' for session {session_id}")
                                manager.awaiting_response[session_id] = True
                                seq_for_text = manager.next_sequence(session_id)
                                await manager.add_message_to_session(session_id, MessageSpeaker.STUDENT, text_input)
                                await conn.conversation.item.create(item={
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": text_input}]
                                })
                                await conn.response.create()
                                await manager.send_to_client(session_id, {
                                    "type": "text_message_sent",
                                    "text": text_input,
                                    "speaker": "student",
                                    "seq": seq_for_text
                                })
                            else:
                            else:
                                if not text_input:
                                    logger.warning(f"⚠️ Empty text message received for session {session_id}")
                                elif not manager.openai_connections.get(session_id):
                                    logger.warning(f"⚠️ No OpenAI connection for session {session_id}")
                                elif manager.awaiting_response.get(session_id, False):
                                    logger.warning(f"⚠️ Already awaiting response for session {session_id}")

                        elif message_type == "end_session":
                            # End session and generate feedback
                            logger.info(f"🔚 Processing end_session for {session_id}")
                            
                            # Get the most current session data using our helper method
                            session_doc = await manager.find_session_in_db(session_id)
                            
                            logger.info(f"🔍 Session lookup for end_session: {session_id} -> {'Found' if session_doc else 'Not found'}")
                            
                            if session_doc:
                                end_time = datetime.utcnow()
                                start_time = session_doc.get("start_time", end_time)
                                
                                # Calculate duration with sanity check
                                duration = int((end_time - start_time).total_seconds())
                                
                                # If duration is unreasonably long (>24 hours), use a reasonable default
                                if duration > 86400:  # 24 hours
                                    logger.warning(f"⚠️ Unreasonable duration calculated: {duration}s. Using session manager data or default.")
                                    # Try to get duration from session manager or use a reasonable default
                                    session_data = manager.session_data.get(session_id, {}).get("session", {})
                                    duration = session_data.get("duration", 300)  # Default to 5 minutes
                                    if duration == 0:
                                        duration = 300
                                
                                logger.info(f"📊 Final session duration: {duration}s ({duration//60}m {duration%60}s)")
                                
                                # Get current transcript from database
                                current_transcript = session_doc.get("transcript", [])
                                message_count = len(current_transcript)
                                
                                logger.info(f"📊 Session stats: duration={duration}s, messages={message_count}")
                                
                                # Generate simple feedback based on actual data
                                score = min(100, max(50, 70 + (duration // 60) * 2 + (message_count // 5) * 3))
                                feedback = f"Session completed successfully! Duration: {duration//60}m {duration%60}s, Messages exchanged: {message_count}"
                                
                                # Prepare comprehensive session update
                                updated_session_data = {
                                    "status": SessionStatus.COMPLETED,
                                    "end_time": end_time,
                                    "duration": duration,
                                    "score": score,
                                    "feedback": feedback,
                                    "updated_at": datetime.utcnow()
                                }
                                
                                # Update session in database - use the same ID format as the found session
                                session_update_id = session_doc["_id"]
                                
                                logger.info(f"🔄 Updating session {session_id} with data: {updated_session_data}")
                                
                                update_result = await sessions_collection.update_one(
                                    {"_id": session_update_id},
                                    {"$set": updated_session_data}
                                )
                                
                                if update_result.modified_count > 0:
                                    logger.info(f"✅ Session {session_id} updated successfully")
                                    # Verify the update
                                    verification = await sessions_collection.find_one({"_id": session_update_id})
                                    logger.info(f"✅ Verified update - status: {verification.get('status')}, duration: {verification.get('duration')}, end_time: {verification.get('end_time')}")
                                else:
                                    logger.error(f"❌ Session {session_id} update failed - matched: {update_result.matched_count}, modified: {update_result.modified_count}")
                                    logger.error(f"❌ Update data was: {updated_session_data}")
                                    logger.error(f"❌ Session ID used: {session_update_id} (type: {type(session_update_id)})")
                                
                                # Get the fully updated session document
                                final_session_doc = await sessions_collection.find_one({"_id": session_update_id})
                                
                                # Get transcript text for recording
                                transcript_text = await manager.get_session_transcript(session_id)
                                
                                # Generate session analysis
                                analysis_text = await manager.generate_session_analysis(
                                    session_id, transcript_text, final_session_doc
                                )
                                
                                # Get patient data for recording
                                patient_data = manager.session_data.get(session_id, {}).get("patient", {})
                                
                                # Save recording with transcript and analysis
                                recording_id = await manager.save_recording(
                                    session_id=session_id,
                                    session_data=final_session_doc,
                                    patient_data=patient_data,
                                    transcription=transcript_text,
                                    analysis=analysis_text,
                                    audio_url=None  # TODO: Implement audio storage if needed
                                )
                                
                                logger.info(f"📝 Session {session_id} completed and recorded (Recording ID: {recording_id})")
                                
                                # Send session ended message with all data
                                session_ended_message = {
                                    "type": "session_ended",
                                    "session_id": session_id,
                                    "duration": duration,
                                    "score": score,
                                    "feedback": feedback,
                                    "message_count": message_count,
                                    "recording_id": recording_id,
                                    "transcript_length": len(transcript_text) if transcript_text else 0
                                }
                                
                                logger.info(f"📤 Sending session_ended message: {session_ended_message}")
                                await manager.send_to_client(session_id, session_ended_message)
                                
                                # Give the client time to process the message
                                await asyncio.sleep(1.0)
                                
                                logger.info(f"🔚 Closing WebSocket for session {session_id}")
                            else:
                                logger.error(f"❌ Session {session_id} not found for end_session")
                            
                            await websocket.close(code=1000, reason="Session ended")
                            break

                    except json.JSONDecodeError:
                        logger.error("Failed to decode client message")
                    except Exception as e:
                        logger.error(f"Error processing client message: {e}")

    except WebSocketDisconnect:
        logger.info(f"Session {session_id} disconnected (reason={disconnect_reason})")
    except Exception as e:
        disconnect_reason = f"exception:{e}"
        logger.error(f"WebSocket error (session={session_id}): {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            pass
    finally:
        # Cancel heartbeat first
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task

        # Cancel OpenAI realtime task BEFORE removing active connection
        if openai_task and not openai_task.done():
            openai_task.cancel()
            with suppress(asyncio.CancelledError):
                await openai_task

        if session_id and manager.session_generations.get(session_id) == generation:
            logger.info(f"🧹 Cleaning up session {session_id} (final_reason={disconnect_reason}) gen={generation}")
            manager.disconnect(session_id)
        else:
            if session_id:
                logger.info(f"🧹 Skipping disconnect for stale generation session={session_id} gen={generation} current_gen={manager.session_generations.get(session_id)}")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "voice-realtime-api"}

@router.post("/test-connection")
async def test_openai_connection(current_user: User = Depends(get_current_user)):
    """Test OpenAI API connection"""
    try:
        if not settings.OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OpenAI API key not found")
        
        if not openai_client:
            raise HTTPException(status_code=500, detail="OpenAI client not initialized")
        
        await openai_client.models.list()
        return {"status": "success", "message": "OpenAI connection successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")

@router.get("/active-sessions")
async def get_active_sessions(current_user: User = Depends(get_current_user)):
    """Get active voice sessions count"""
    return {
        "active_connections": len(manager.active_connections),
        "openai_connections": len(manager.openai_connections),
        "session_data": len(manager.session_data)
    }

@router.get("/recordings/{session_id}")
async def get_session_recording(session_id: str, current_user: User = Depends(get_current_user)):
    """Get recording data for a specific session"""
    try:
        recordings_collection = get_recordings_collection()
        
        # Find recording by session_id
        recording = await recordings_collection.find_one({"session_id": session_id})
        
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # Verify user owns this recording
        if recording.get("student_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied - not your recording")
        
        # Convert ObjectId to string for JSON serialization
        recording["_id"] = str(recording["_id"])
        
        return recording
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving recording for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve recording: {str(e)}")

@router.get("/recordings")
async def get_user_recordings(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=10, le=100),
    skip: int = Query(default=0, ge=0)
):
    """Get all recordings for the current user"""
    try:
        recordings_collection = get_recordings_collection()
        
        # Find recordings for the current user
        cursor = recordings_collection.find(
            {"student_id": current_user.id}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        recordings = []
        async for recording in cursor:
            recording["_id"] = str(recording["_id"])
            recordings.append(recording)
        
        # Get total count
        total_count = await recordings_collection.count_documents({"student_id": current_user.id})
        
        return {
            "recordings": recordings,
            "total": total_count,
            "limit": limit,
            "skip": skip
        }
        
    except Exception as e:
        logger.error(f"❌ Error retrieving recordings for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve recordings: {str(e)}")