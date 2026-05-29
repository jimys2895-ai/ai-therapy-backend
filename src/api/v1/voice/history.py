from fastapi import APIRouter, HTTPException, Depends, status, Query, Path
from fastapi.responses import StreamingResponse
from typing import List, Optional
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from gridfs import GridFS
import io

from ....database import get_sessions_collection, get_patients_collection, get_recordings_collection
from ....models.history import (
    Session, SessionCreate, SessionResponse, SessionUpdate, 
    AddMessageRequest, SessionStats, SessionHistoryFilter,
    TranscriptMessage, MessageSpeaker, SessionStatus
)
from ....auth.dependencies import get_current_user
from ....models.users import User

router = APIRouter()

# Response models for OpenAPI documentation
class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message", example="Operation completed successfully")

class SessionListResponse(BaseModel):
    sessions: List[SessionResponse] = Field(..., description="List of therapy sessions")
    total_count: int = Field(..., description="Total number of sessions", example=12)

class EndSessionResponse(BaseModel):
    message: str = Field(..., description="Session completion message")
    duration: int = Field(..., description="Session duration in seconds", example=2700)
    score: int = Field(..., description="AI-generated performance score (0-100)", example=87)
    feedback: str = Field(..., description="AI-generated feedback")

class AddMessageResponse(BaseModel):
    message: str = Field(..., description="Success message")
    message_id: str = Field(..., description="ID of the added message")


@router.post("/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create therapy session",
    description="Start a new therapy training session with a patient persona",
    responses={
        201: {
            "description": "Session created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "student_id": "507f1f77bcf86cd799439012",
                        "patient_id": "507f1f77bcf86cd799439013",
                        "start_time": "2024-01-21T14:30:00Z",
                        "status": "active",
                        "audio_enabled": True,
                        "voice_type": "female",
                        "voice_speed": 1.0
                    }
                }
            }
        },
        404: {"description": "Patient not found"},
        403: {"description": "Can only create sessions for yourself"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to create session"}
    }
)
async def create_session(
    session_data: SessionCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new therapy training session.
    
    - **patient_id**: ID of the patient persona to practice with
    - **audio_enabled**: Enable voice features for the session
    - **voice_type**: Preferred AI voice type (optional)
    - **voice_speed**: Speech speed multiplier (optional)
    
    The student_id is automatically set from the authenticated user.
    Starts an active session that can be used for real-time therapy practice
    with AI-powered patient personas.
    """
    # Add logging at the very beginning
    print(f"=== SESSION CREATION START ===")
    print(f"Function called with session_data type: {type(session_data)}")
    print(f"Current user type: {type(current_user)}")
    print(f"Raw session_data: {session_data}")
    print(f"Session data model dump: {session_data.model_dump() if hasattr(session_data, 'model_dump') else 'No model_dump'}")
    
    try:
        sessions_collection = get_sessions_collection()
        patients_collection = get_patients_collection()
        
        # Enhanced logging for debugging
        print(f"=== SESSION CREATION DEBUG ===")
        print(f"Received session_data: {session_data}")
        print(f"Session data dict: {session_data.dict() if hasattr(session_data, 'dict') else 'No dict method'}")
        print(f"Patient ID: {session_data.patient_id}")
        print(f"Patient ID type: {type(session_data.patient_id)}")
        print(f"Current user ID: {current_user.id}")
        print(f"Current user type: {type(current_user.id)}")
        
        # Verify patient exists - try both string and ObjectId formats
        patient = None
        
        # First try with the ID as-is (string)
        patient = await patients_collection.find_one({"_id": session_data.patient_id})
        
        # If not found, try converting to ObjectId
        if not patient:
            try:
                patient_object_id = ObjectId(session_data.patient_id)
                patient = await patients_collection.find_one({"_id": patient_object_id})
            except Exception:
                pass
        
        if not patient:
            # Log for debugging
            print(f"Patient not found with ID: {session_data.patient_id}")
            # Try to list all patients to debug
            all_patients = await patients_collection.find({}).to_list(length=10)
            print(f"Available patients: {[p.get('_id') for p in all_patients]}")
            print(f"Patient ID types: {[type(p.get('_id')) for p in all_patients]}")
            print(f"=== END SESSION CREATION DEBUG ===")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient not found with ID: {session_data.patient_id}"
            )
        
        print(f"Patient found: {patient.get('name', 'Unknown')}")
        print(f"=== END SESSION CREATION DEBUG ===")
        
        # Create session document
        session_doc = {
            "_id": str(ObjectId()),
            "student_id": current_user.id,  # Use current user's ID instead of from request
            "patient_id": session_data.patient_id,  # Use the original patient_id as provided
            "start_time": datetime.utcnow(),
            "end_time": None,
            "transcript": [],
            "duration": 0,
            "score": None,
            "feedback": None,
            "status": SessionStatus.ACTIVE,
            "session_notes": None,
            "ai_analysis": None,
            "performance_metrics": None,
            "audio_enabled": session_data.audio_enabled,
            "voice_type": session_data.voice_type,
            "voice_speed": session_data.voice_speed,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Insert session
        await sessions_collection.insert_one(session_doc)
        
        return SessionResponse(**session_doc)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.get("/sessions",
    response_model=SessionListResponse,
    summary="Get user sessions",
    description="Retrieve therapy sessions for the current user with filtering and pagination",
    responses={
        200: {
            "description": "Sessions retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "sessions": [
                            {
                                "id": "507f1f77bcf86cd799439011",
                                "student_id": "507f1f77bcf86cd799439012",
                                "patient_id": "507f1f77bcf86cd799439013",
                                "start_time": "2024-01-21T14:30:00Z",
                                "end_time": "2024-01-21T15:15:00Z",
                                "duration": 2700,
                                "score": 87,
                                "status": "completed",
                                "feedback": "Excellent session! Strong empathy and active listening."
                            }
                        ],
                        "total_count": 12
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve sessions"}
    }
)
async def get_user_sessions(
    patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
    status_filter: Optional[SessionStatus] = Query(None, description="Filter by session status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip for pagination"),
    sort_by: str = Query("start_time", regex="^(start_time|score|duration)$", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order (asc/desc)"),
    current_user: User = Depends(get_current_user)
):
    """
    Get therapy sessions for the current user with filtering and pagination.
    
    - **patient_id**: Filter sessions by specific patient persona
    - **status_filter**: Filter by session status (active, completed, paused, cancelled)
    - **limit**: Maximum number of sessions to return (1-100)
    - **offset**: Number of sessions to skip for pagination
    - **sort_by**: Field to sort by (start_time, score, duration)
    - **sort_order**: Sort order (asc for ascending, desc for descending)
    
    Returns paginated list of sessions with comprehensive session data including
    transcripts, scores, and AI-generated feedback.
    """
    try:
        sessions_collection = get_sessions_collection()
        
        # Build filter query - users can only see their own sessions
        filter_query = {"student_id": current_user.id}
        
        if patient_id:
            filter_query["patient_id"] = patient_id
        if status_filter:
            filter_query["status"] = status_filter
        
        # Build sort query
        sort_direction = 1 if sort_order == "asc" else -1
        sort_query = [(sort_by, sort_direction)]
        
        # Get sessions with pagination
        cursor = sessions_collection.find(filter_query).sort(sort_query).skip(offset).limit(limit)
        sessions = await cursor.to_list(length=None)
        
        # Get total count for pagination
        total_count = await sessions_collection.count_documents(filter_query)
        
        if not sessions:
            return SessionListResponse(sessions=[], total_count=0)
        
        # Enrich sessions with patient names
        patients_collection = get_patients_collection()
        for session in sessions:
            patient_id = session.get("patient_id")
            if patient_id:
                # Try to find patient by string ID first
                patient = await patients_collection.find_one({"_id": patient_id})
                # If not found, try ObjectId
                if not patient:
                    try:
                        patient = await patients_collection.find_one({"_id": ObjectId(patient_id)})
                    except:
                        pass
                
                if patient:
                    session["patient_name"] = patient.get("name", "Unknown Patient")
                else:
                    session["patient_name"] = f"Patient {patient_id}"
            else:
                session["patient_name"] = "Unknown Patient"
        
        session_responses = [SessionResponse(**session) for session in sessions]
        return SessionListResponse(sessions=session_responses, total_count=total_count)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sessions: {str(e)}"
        )


@router.get("/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get session by ID",
    description="Retrieve detailed information about a specific therapy session",
    responses={
        200: {
            "description": "Session retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "student_id": "507f1f77bcf86cd799439012",
                        "patient_id": "507f1f77bcf86cd799439013",
                        "start_time": "2024-01-21T14:30:00Z",
                        "end_time": "2024-01-21T15:15:00Z",
                        "duration": 2700,
                        "score": 87,
                        "status": "completed",
                        "feedback": "Excellent session! Strong empathy and active listening.",
                        "transcript": [
                            {
                                "id": "msg1",
                                "speaker": "student",
                                "text": "Hello, how are you feeling today?",
                                "timestamp": "2024-01-21T14:30:15Z"
                            }
                        ]
                    }
                }
            }
        },
        404: {"description": "Session not found"},
        403: {"description": "You can only access your own sessions"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve session"}
    }
)
async def get_session(
    session_id: str = Path(..., description="Session ID to retrieve", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific therapy session.
    
    Returns comprehensive session data including:
    - Complete conversation transcript
    - AI-generated performance score and feedback
    - Session duration and timing
    - Audio settings used during the session
    """
    try:
        sessions_collection = get_sessions_collection()
        
        session = await sessions_collection.find_one({"_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Check if user owns this session
        if session["student_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own sessions"
            )
        
        return SessionResponse(**session)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve session: {str(e)}"
        )


@router.put("/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Update session",
    description="Update session information such as notes, status, or feedback",
    responses={
        200: {
            "description": "Session updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "student_id": "507f1f77bcf86cd799439012",
                        "patient_id": "507f1f77bcf86cd799439013",
                        "status": "completed",
                        "session_notes": "Patient showed good progress",
                        "updated_at": "2024-01-21T15:15:00Z"
                    }
                }
            }
        },
        404: {"description": "Session not found"},
        403: {"description": "You can only update your own sessions"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to update session"}
    }
)
async def update_session(
    session_update: SessionUpdate,
    session_id: str = Path(..., description="Session ID to update", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(get_current_user)
):
    """
    Update session information.
    
    Allows updating various session fields including:
    - Session status (active, completed, paused, cancelled)
    - Session notes and observations
    - AI analysis results
    - Performance metrics
    
    Duration is automatically calculated when end_time is provided.
    """
    try:
        sessions_collection = get_sessions_collection()
        
        # Check if session exists and user owns it
        existing_session = await sessions_collection.find_one({"_id": session_id})
        if not existing_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if existing_session["student_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own sessions"
            )
        
        # Prepare update data
        update_data = {k: v for k, v in session_update.dict().items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()
        
        # Calculate duration if end_time is provided
        if session_update.end_time and existing_session.get("start_time"):
            start_time = existing_session["start_time"]
            end_time = session_update.end_time
            duration = int((end_time - start_time).total_seconds())
            update_data["duration"] = duration
        
        # Update session
        await sessions_collection.update_one(
            {"_id": session_id},
            {"$set": update_data}
        )
        
        # Get updated session
        updated_session = await sessions_collection.find_one({"_id": session_id})
        return SessionResponse(**updated_session)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}"
        )


@router.post("/sessions/{session_id}/messages",
    response_model=AddMessageResponse,
    summary="Add message to session",
    description="Add a new message to the session transcript",
    responses={
        200: {
            "description": "Message added successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Message added successfully",
                        "message_id": "507f1f77bcf86cd799439014"
                    }
                }
            }
        },
        404: {"description": "Session not found"},
        403: {"description": "You can only add messages to your own sessions"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to add message"}
    }
)
async def add_message_to_session(
    message_data: AddMessageRequest,
    session_id: str = Path(..., description="Session ID to add message to", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(get_current_user)
):
    """
    Add a new message to the session transcript.
    
    - **speaker**: Who is speaking (student or patient)
    - **text**: The message content
    - **audio_url**: Optional URL to audio recording of the message
    
    Messages are automatically timestamped and added to the session's
    conversation transcript for later review and analysis.
    """
    try:
        sessions_collection = get_sessions_collection()
        
        # Check if session exists and user owns it
        existing_session = await sessions_collection.find_one({"_id": session_id})
        if not existing_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if existing_session["student_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only add messages to your own sessions"
            )
        
        # Create new message
        new_message = TranscriptMessage(
            id=str(ObjectId()),
            speaker=message_data.speaker,
            text=message_data.text,
            timestamp=datetime.utcnow(),
            audio_url=message_data.audio_url
        )
        
        # Add message to transcript
        await sessions_collection.update_one(
            {"_id": session_id},
            {
                "$push": {"transcript": new_message.dict()},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        return {"message": "Message added successfully", "message_id": new_message.id}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add message: {str(e)}"
        )


@router.post("/sessions/{session_id}/end",
    response_model=EndSessionResponse,
    summary="End therapy session",
    description="Complete a therapy session and generate AI feedback and scoring",
    responses={
        200: {
            "description": "Session ended successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Session ended successfully",
                        "duration": 2700,
                        "score": 87,
                        "feedback": "Excellent session! You demonstrated strong empathy and active listening skills."
                    }
                }
            }
        },
        404: {"description": "Session not found"},
        403: {"description": "You can only end your own sessions"},
        400: {"description": "Session is not active"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to end session"}
    }
)
async def end_session(
    session_id: str = Path(..., description="Session ID to end", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(get_current_user)
):
    """
    End a therapy session and generate AI feedback.
    
    Completes an active session by:
    - Calculating total session duration
    - Generating AI-powered performance score (0-100)
    - Providing detailed feedback on therapeutic techniques
    - Updating session status to completed
    
    The AI analyzes conversation patterns, empathy demonstration,
    and therapeutic approach to provide constructive feedback.
    """
    try:
        sessions_collection = get_sessions_collection()
        
        # Check if session exists and user owns it
        existing_session = await sessions_collection.find_one({"_id": session_id})
        if not existing_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if existing_session["student_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only end your own sessions"
            )
        
        if existing_session["status"] != SessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is not active"
            )
        
        # Calculate session duration
        end_time = datetime.utcnow()
        start_time = existing_session["start_time"]
        duration = int((end_time - start_time).total_seconds())
        
        # Generate mock AI feedback and score
        feedback_options = [
            "Excellent session! You demonstrated strong empathy and active listening skills. Your questions were well-structured and helped the patient open up effectively.",
            "Good therapeutic approach. You maintained appropriate boundaries while showing genuine concern. Consider exploring deeper emotional responses next time.",
            "Well done on building rapport quickly. Your communication style was professional yet warm. Work on summarizing patient concerns more frequently.",
            "Strong session with good therapeutic presence. You handled difficult moments well. Focus on using more open-ended questions to encourage elaboration.",
            "Very professional approach. You showed excellent patience and understanding. Consider incorporating more reflective listening techniques."
        ]
        
        import random
        feedback = random.choice(feedback_options)
        score = random.randint(75, 95)  # Mock score between 75-95
        
        # Update session
        update_data = {
            "end_time": end_time,
            "duration": duration,
            "status": SessionStatus.COMPLETED,
            "feedback": feedback,
            "score": score,
            "updated_at": datetime.utcnow()
        }
        
        await sessions_collection.update_one(
            {"_id": session_id},
            {"$set": update_data}
        )
        
        return {
            "message": "Session ended successfully",
            "duration": duration,
            "score": score,
            "feedback": feedback
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end session: {str(e)}"
        )


@router.get("/stats", response_model=SessionStats)
async def get_user_stats(
    current_user: User = Depends(get_current_user)
):
    """Get session statistics for the current user"""
    try:
        sessions_collection = get_sessions_collection()
        
        # Get all completed sessions for the user
        completed_sessions = await sessions_collection.find({
            "student_id": current_user.id,
            "status": SessionStatus.COMPLETED
        }).to_list(length=None)
        
        if not completed_sessions:
            return SessionStats(
                total_sessions=0,
                average_score=0.0,
                hours_completed=0.0,
                current_streak=0,
                sessions_this_week=0,
                sessions_this_month=0,
                improvement_trend=0.0
            )
        
        # Calculate statistics
        total_sessions = len(completed_sessions)
        total_duration = sum(session.get("duration", 0) for session in completed_sessions)
        hours_completed = total_duration / 3600  # Convert seconds to hours
        
        # Calculate average score
        scores = [session.get("score", 0) for session in completed_sessions if session.get("score")]
        average_score = sum(scores) / len(scores) if scores else 0.0
        
        # Calculate sessions this week and month
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        def _ensure_utc(dt) -> datetime:
            if not isinstance(dt, datetime):
                return datetime.min.replace(tzinfo=timezone.utc)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        sessions_this_week = len([
            s for s in completed_sessions
            if _ensure_utc(s.get("start_time")) >= week_ago
        ])

        sessions_this_month = len([
            s for s in completed_sessions
            if _ensure_utc(s.get("start_time")) >= month_ago
        ])

        # Calculate current streak (consecutive days with sessions)
        current_streak = 0
        sessions_by_date = {}
        for session in completed_sessions:
            date = _ensure_utc(session.get("start_time")).date()
            sessions_by_date[date] = sessions_by_date.get(date, 0) + 1
        
        current_date = now.date()
        while current_date in sessions_by_date:
            current_streak += 1
            current_date -= timedelta(days=1)
        
        # Calculate improvement trend (simple version)
        improvement_trend = 0.0
        if len(scores) >= 2:
            recent_scores = scores[-5:]  # Last 5 sessions
            early_scores = scores[:5]   # First 5 sessions
            if early_scores:
                recent_avg = sum(recent_scores) / len(recent_scores)
                early_avg = sum(early_scores) / len(early_scores)
                improvement_trend = ((recent_avg - early_avg) / early_avg) * 100
        
        return SessionStats(
            total_sessions=total_sessions,
            average_score=round(average_score, 1),
            hours_completed=round(hours_completed, 1),
            current_streak=current_streak,
            sessions_this_week=sessions_this_week,
            sessions_this_month=sessions_this_month,
            improvement_trend=round(improvement_trend, 1)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve stats: {str(e)}"
        )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a session"""
    try:
        sessions_collection = get_sessions_collection()
        
        # Check if session exists and user owns it
        existing_session = await sessions_collection.find_one({"_id": session_id})
        if not existing_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if existing_session["student_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own sessions"
            )
        
        # Delete session
        await sessions_collection.delete_one({"_id": session_id})
        
        return {"message": "Session deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}"
        )


@router.get("/sessions/{session_id}/recording")
async def download_session_recording(
    session_id: str = Path(..., description="Session ID to download recording for"),
    current_user: User = Depends(get_current_user)
):
    """Download session audio recording"""
    try:
        sessions_collection = get_sessions_collection()
        
        # Check if session exists and user owns it
        session = await sessions_collection.find_one({"_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if session["student_id"] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only download your own session recordings"
            )
        
        # Check if session has audio recording
        audio_file_id = session.get("audio_file_id")
        if not audio_file_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No audio recording found for this session"
            )
        
        # Get audio file from GridFS
        fs = GridFS(sessions_collection.database)
        try:
            audio_file = fs.get(ObjectId(audio_file_id))
            
            # Create streaming response
            def generate():
                while True:
                    chunk = audio_file.read(8192)  # Read in 8KB chunks
                    if not chunk:
                        break
                    yield chunk
            
            return StreamingResponse(
                generate(),
                media_type="audio/wav",
                headers={
                    "Content-Disposition": f"attachment; filename=session_{session_id}.wav"
                }
            )
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found in storage"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download recording: {str(e)}"
        )


@router.get("/recordings")
async def get_user_recordings(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of recordings to return"),
    offset: int = Query(0, ge=0, description="Number of recordings to skip for pagination"),
    current_user: User = Depends(get_current_user)
):
    """Get user's session recordings"""
    try:
        recordings_collection = get_recordings_collection()
        
        # Get recordings for the current user
        cursor = recordings_collection.find(
            {"student_id": current_user.id}
        ).sort("created_at", -1).skip(offset).limit(limit)
        
        recordings = await cursor.to_list(length=None)
        total_count = await recordings_collection.count_documents({"student_id": current_user.id})
        
        return {
            "recordings": recordings,
            "total_count": total_count
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve recordings: {str(e)}"
        )