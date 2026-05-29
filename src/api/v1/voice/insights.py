"""
HIPAA-Compliant Therapy Session Analysis and Scoring Module

This module provides AI-powered analysis of therapy training sessions
with strict scoring criteria for student therapist evaluation.
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
import openai

from ....config import settings
from ....database import get_sessions_collection, get_patients_collection
from ....auth.dependencies import get_current_user
from ....models.users import User
from ....models.history import SessionInsights, TherapySkillScore, SessionStatus

# Setup logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

# Initialize OpenAI client
openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if hasattr(settings, 'OPENAI_API_KEY') else None

def calculate_grade(score: int) -> str:
    """Convert numerical score to letter grade with strict standards"""
    if score >= 97: return "A+"
    elif score >= 93: return "A"
    elif score >= 90: return "A-"
    elif score >= 87: return "B+"
    elif score >= 83: return "B"
    elif score >= 80: return "B-"
    elif score >= 77: return "C+"
    elif score >= 73: return "C"
    elif score >= 70: return "C-"
    elif score >= 67: return "D+"
    elif score >= 60: return "D"
    else: return "F"

def analyze_talk_time(transcript: List[Dict]) -> tuple[float, float]:
    """Analyze student vs patient talk time percentages"""
    student_words = 0
    patient_words = 0
    
    for message in transcript:
        word_count = len(message.get("text", "").split())
        if message.get("speaker") == "student":
            student_words += word_count
        elif message.get("speaker") == "patient":
            patient_words += word_count
    
    total_words = student_words + patient_words
    if total_words == 0:
        return 0.0, 0.0
    
    return (student_words / total_words * 100), (patient_words / total_words * 100)

@router.post("/generate/{session_id}")
async def generate_insights_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Generate insights for a completed session
    
    Args:
        session_id: The session ID to generate insights for
        current_user: Authenticated user
    
    Returns:
        SessionInsights: Generated insights for the session
    """
    try:
        logger.info(f"🧠 Generating insights for session {session_id} by user {current_user.email}")
        logger.info(f"📊 Session ID format: {type(session_id)} - {session_id}")
        
        # Get collections
        sessions_collection = get_sessions_collection()
        patients_collection = get_patients_collection()
        
        # Find session - try both ObjectId and string formats
        session = None
        if ObjectId.is_valid(session_id):
            session = await sessions_collection.find_one({"_id": ObjectId(session_id)})
        if not session:
            session = await sessions_collection.find_one({"_id": session_id})
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Debug: Log session data structure
        logger.info(f"🔍 Session data keys: {list(session.keys())}")
        logger.info(f"🔍 Session status: {session.get('status')}")
        logger.info(f"🔍 Session start_time: {session.get('start_time')} (type: {type(session.get('start_time'))})")
        logger.info(f"🔍 Session end_time: {session.get('end_time')} (type: {type(session.get('end_time'))})")
        
        # Verify user owns this session
        if session.get("student_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied - not your session")
        
        # Check if insights already exist
        if session.get("insights_generated", False):
            existing_insights = session.get("insights")
            if existing_insights:
                logger.info(f"✅ Returning existing insights for session {session_id}")
                return SessionInsights(**existing_insights)
        
        # Get patient data
        patient_id = session.get("patient_id")
        logger.info(f"🔍 Looking for patient with ID: {patient_id} (type: {type(patient_id)})")
        
        patient = None
        if patient_id:
            if ObjectId.is_valid(patient_id):
                patient = await patients_collection.find_one({"_id": ObjectId(patient_id)})
            if not patient:
                patient = await patients_collection.find_one({"_id": patient_id})
        
        if not patient:
            logger.error(f"❌ Patient not found with ID: {patient_id}")
            raise HTTPException(status_code=404, detail="Patient not found")
        
        logger.info(f"✅ Found patient: {patient.get('name', 'Unknown')}")
        
        # Calculate duration - handle None values
        start_time = session.get("start_time")
        end_time = session.get("end_time")
        
        # Provide defaults if times are None
        if start_time is None:
            start_time = datetime.utcnow()
            logger.warning(f"⚠️ No start_time found for session {session_id}, using current time")
        
        if end_time is None:
            end_time = datetime.utcnow()
            logger.warning(f"⚠️ No end_time found for session {session_id}, using current time")
        
        # Calculate duration safely
        try:
            duration = int((end_time - start_time).total_seconds())
        except Exception as e:
            logger.error(f"❌ Error calculating duration: {e}")
            # Try to use pre-calculated duration from session
            duration = session.get("duration", 0)
            if duration == 0:
                logger.warning(f"⚠️ No duration available, using default of 300 seconds")
                duration = 300  # Default to 5 minutes
        
        # Get transcript - refresh session data to ensure we have the latest
        refreshed_session = await sessions_collection.find_one({"_id": session["_id"]})
        if refreshed_session:
            session = refreshed_session
            logger.info(f"🔄 Refreshed session data for insights generation")
        
        transcript = session.get("transcript", [])
        
        if not transcript:
            logger.warning(f"⚠️ No transcript found for session {session_id}")
            logger.warning(f"⚠️ Session keys: {list(session.keys())}")
            logger.warning(f"⚠️ Session status: {session.get('status')}")
        else:
            logger.info(f"📊 Found {len(transcript)} transcript messages")
            # Log first few messages for debugging
            for i, msg in enumerate(transcript[:3]):
                logger.info(f"🔍 Message {i}: speaker={msg.get('speaker')}, text_length={len(msg.get('text', ''))}")
        
        logger.info(f"📊 Generating insights for session {session_id} with {len(transcript)} messages, {duration}s duration")
        
        # If transcript is empty, wait a moment and try refreshing again
        if not transcript:
            logger.info(f"⏳ Transcript empty, waiting 2 seconds and refreshing...")
            await asyncio.sleep(2)
            final_refresh = await sessions_collection.find_one({"_id": session["_id"]})
            if final_refresh:
                transcript = final_refresh.get("transcript", [])
                logger.info(f"🔄 After final refresh: {len(transcript)} transcript messages")
        
        # Generate insights
        insights = await generate_session_insights(session, patient, transcript, duration)
        
        # Save insights to database with comprehensive update
        session_update_id = session["_id"]
        update_data = {
            "insights": insights.dict(),
            "insights_generated": True,
            "updated_at": datetime.utcnow()
        }
        
        # Only update status if it's not already completed
        if session.get("status") != SessionStatus.COMPLETED:
            update_data["status"] = SessionStatus.COMPLETED
        
        # Also update legacy fields for backward compatibility
        update_data.update({
            "score": insights.overall_score,
            "feedback": insights.session_summary,
            "ai_analysis": {
                "overall_score": insights.overall_score,
                "grade": insights.grade,
                "skill_scores": {
                    "active_listening": insights.active_listening.dict(),
                    "empathy_demonstration": insights.empathy_demonstration.dict(),
                    "questioning_techniques": insights.questioning_techniques.dict(),
                    "boundary_maintenance": insights.boundary_maintenance.dict(),
                    "crisis_management": insights.crisis_management.dict(),
                    "therapeutic_interventions": insights.therapeutic_interventions.dict()
                },
                "talk_time_analysis": {
                    "student_percentage": insights.student_talk_percentage,
                    "patient_percentage": insights.patient_talk_percentage
                },
                "recommendations": {
                    "immediate": insights.immediate_feedback,
                    "long_term": insights.long_term_development,
                    "resources": insights.recommended_resources
                },
                "risk_assessment": {
                    "flags": insights.risk_flags,
                    "supervisor_review_required": insights.supervisor_review_required
                }
            }
        })
        
        update_result = await sessions_collection.update_one(
            {"_id": session_update_id},
            {"$set": update_data}
        )
        
        if update_result.modified_count > 0:
            logger.info(f"✅ Session {session_id} updated with insights successfully")
        else:
            logger.warning(f"⚠️ Session {session_id} insights update failed")
        
        logger.info(f"✅ Insights generated and saved for session {session_id} with score: {insights.overall_score} ({insights.grade})")
        
        return insights
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating insights for session {session_id}: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate insights: {str(e)}")


@router.get("/{session_id}")
async def get_session_insights(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get existing insights for a session
    
    Args:
        session_id: The session ID to get insights for
        current_user: Authenticated user
    
    Returns:
        SessionInsights: Existing insights for the session
    """
    try:
        logger.info(f"📖 Getting insights for session {session_id} by user {current_user.email}")
        
        # Get session
        sessions_collection = get_sessions_collection()
        session = None
        if ObjectId.is_valid(session_id):
            session = await sessions_collection.find_one({"_id": ObjectId(session_id)})
        if not session:
            session = await sessions_collection.find_one({"_id": session_id})
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify user owns this session
        if session.get("student_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied - not your session")
        
        # Check if insights exist
        insights_data = session.get("insights")
        if not insights_data:
            raise HTTPException(status_code=404, detail="Insights not found - generate insights first")
        
        return SessionInsights(**insights_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting insights for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get insights: {str(e)}")


async def generate_session_insights(
    session_data: Dict[str, Any],
    patient_data: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    duration: int
) -> SessionInsights:
    """
    Generate comprehensive HIPAA-compliant session insights using GPT-4o-mini
    
    Args:
        session_data: Session metadata
        patient_data: De-identified patient information
        transcript: Session transcript with speaker identification
        duration: Session duration in seconds
    
    Returns:
        SessionInsights: Comprehensive analysis and scoring
    """
    
    logger.info(f"🧠 Starting insights generation for session with {len(transcript)} messages, {duration}s duration")
    
    if not openai_client:
        logger.error("❌ OpenAI client not initialized")
        raise Exception("OpenAI client not initialized")
    
    if not transcript or len(transcript) == 0:
        logger.warning("⚠️ No transcript data available for analysis")
        return _create_default_insights(50.0, 50.0, duration)
    
    # Analyze talk time
    student_talk_pct, patient_talk_pct = analyze_talk_time(transcript)
    
    # Prepare transcript text
    transcript_text = ""
    for msg in transcript:
        speaker = "Student Therapist" if msg.get("speaker") == "student" else "Patient"
        transcript_text += f"{speaker}: {msg.get('text', '')}\n"
    
    # Create comprehensive analysis prompt - use string concatenation to avoid f-string issues with JSON
    session_context = f"""
    SESSION CONTEXT:
    - Duration: {duration} seconds ({duration//60} minutes)
    - Patient Condition: {patient_data.get('condition', 'Not specified')}
    - Patient Emotional State: {patient_data.get('emotional_state', 'Not specified')}
    - Student Talk Time: {student_talk_pct:.1f}%
    - Patient Talk Time: {patient_talk_pct:.1f}%
    
    TRANSCRIPT:
    {transcript_text}
    """
    
    analysis_prompt = """
    You are an expert clinical supervisor evaluating a therapy training session with STRICT HIPAA-compliant standards. 
    This is professional clinical training - be rigorous and demanding in your evaluation.
    
    """ + session_context + """
    
    CRITICAL SESSION REQUIREMENTS (AUTOMATIC DEDUCTIONS):
    - Sessions under 10 minutes: Deduct 20-30 points (insufficient therapeutic time)
    - Sessions under 5 minutes: Maximum score of 40 (inadequate for therapy)
    - Missing proper greeting/introduction: Deduct 10-15 points
    - No session closure or therapeutic ending: Deduct 10-15 points
    - Failure to establish rapport initially: Deduct 10 points
    - No check-in about patient's current state: Deduct 5-10 points
    - Missing confidentiality reminder: Deduct 5 points
    
    EVALUATION CRITERIA (STRICT HIPAA-COMPLIANT STANDARDS):
    
    1. ACTIVE LISTENING (0-100):
    - 95-100: Exceptional reflection, paraphrasing, minimal encouragers, perfect timing
    - 85-94: Strong listening with consistent reflective responses
    - 75-84: Good listening but misses some emotional cues
    - 65-74: Adequate listening, some interruptions or missed opportunities
    - 55-64: Poor listening, frequent interruptions, misses key information
    - <55: Fails to demonstrate basic listening skills, dismissive
    
    2. EMPATHY DEMONSTRATION (0-100):
    - 95-100: Consistently validates emotions, demonstrates deep understanding, appropriate emotional responses
    - 85-94: Good empathy with genuine emotional connection
    - 75-84: Shows empathy but sometimes mechanical or surface-level
    - 65-74: Limited empathy, focuses more on facts than feelings
    - 55-64: Minimal empathy, appears disconnected from patient emotions
    - <55: Lacks empathy, dismissive, judgmental, or inappropriate responses
    
    3. QUESTIONING TECHNIQUES (0-100):
    - 95-100: Masterful use of open-ended questions, perfect timing, facilitates deep exploration
    - 85-94: Excellent questioning with minor timing issues
    - 75-84: Good questions but some leading or closed questions
    - 65-74: Adequate questioning but lacks depth or exploration
    - 55-64: Poor questioning technique, too many closed/leading questions
    - <55: Inappropriate, harmful, or invasive questioning
    
    4. BOUNDARY MAINTENANCE & HIPAA COMPLIANCE (0-100):
    - 95-100: Perfect professional boundaries, complete HIPAA compliance, appropriate self-disclosure
    - 85-94: Strong boundaries with minor lapses, good HIPAA awareness
    - 75-84: Generally appropriate boundaries, some minor concerns
    - 65-74: Some boundary issues, potential HIPAA concerns
    - 55-64: Multiple boundary violations, HIPAA compliance questionable
    - <55: Significant boundary violations, HIPAA breaches, dual relationships
    
    5. CRISIS MANAGEMENT & SAFETY (0-100):
    - 95-100: Excellent crisis assessment, appropriate safety planning, proper referrals
    - 85-94: Good crisis management with minor gaps
    - 75-84: Adequate crisis response but lacks thoroughness
    - 65-74: Limited crisis management skills, some safety concerns
    - 55-64: Poor crisis response, potential safety risks
    - <55: Dangerous crisis management, patient safety compromised
    
    6. THERAPEUTIC INTERVENTIONS & PROFESSIONALISM (0-100):
    - 95-100: Skillful evidence-based techniques, perfect professional language, appropriate interventions
    - 85-94: Good interventions with professional demeanor
    - 75-84: Basic interventions, generally professional
    - 65-74: Limited intervention skills, some unprofessional language
    - 55-64: Poor intervention choices, unprofessional behavior
    - <55: Harmful interventions, highly unprofessional conduct
    
    SESSION STRUCTURE REQUIREMENTS (MANDATORY):
    - Proper greeting and introduction (5-10 points deduction if missing)
    - Confidentiality statement or reminder (5 points deduction if missing)
    - Check-in about patient's current state (5 points deduction if missing)
    - Clear session goals or agenda (5 points deduction if missing)
    - Appropriate session closure with summary (10 points deduction if missing)
    - Scheduling follow-up or next steps (5 points deduction if missing)
    - Professional farewell/well-wishes (5 points deduction if missing)
    
    HIPAA COMPLIANCE CHECKLIST (CRITICAL):
    - No use of patient's real name or identifying information
    - No discussion of other patients or cases
    - Appropriate handling of sensitive information
    - Professional documentation standards
    - Proper consent and confidentiality procedures
    
    AUTOMATIC FAILING SCORES (<60) FOR:
    - Any HIPAA violations or breaches
    - Harmful or dangerous interventions
    - Significant boundary violations
    - Unprofessional or unethical behavior
    - Sessions too brief for therapeutic value (<5 minutes)
    - Missing critical safety assessments when indicated
    
    TALK TIME ANALYSIS (STRICT):
    - Optimal: Student 25-40%, Patient 60-75%
    - Acceptable: Student 20-45%, Patient 55-80%
    - Concerning: Student >50% or <15% (deduct 10-15 points)
    - Problematic: Student >60% or <10% (deduct 20+ points)
    
    ADDITIONAL DEDUCTIONS:
    - Excessive "um," "uh," or filler words: -5 points
    - Inappropriate personal disclosure: -10 points
    - Missing therapeutic alliance building: -10 points
    - No emotional validation: -10 points
    - Rushing through session: -15 points
    - Abrupt or inappropriate ending: -15 points
    
    Respond with a detailed JSON analysis following this EXACT format (replace example values with actual analysis):
    
    {
        "overall_score": 85,
        "session_summary": "Detailed session summary here",
        "patient_engagement_level": "High",
        "therapeutic_rapport": "Good",
        "active_listening": {
            "skill_name": "Active Listening",
            "score": 85,
            "feedback": "Detailed feedback here",
            "strengths": ["Good paraphrasing", "Maintained eye contact"],
            "areas_for_improvement": ["More reflective statements needed"]
        },
        "empathy_demonstration": {
            "skill_name": "Empathy Demonstration", 
            "score": 80,
            "feedback": "Detailed feedback here",
            "strengths": ["Validated emotions well"],
            "areas_for_improvement": ["Could explore feelings deeper"]
        },
        "questioning_techniques": {
            "skill_name": "Questioning Techniques",
            "score": 75,
            "feedback": "Detailed feedback here", 
            "strengths": ["Used open-ended questions"],
            "areas_for_improvement": ["Avoid leading questions"]
        },
        "boundary_maintenance": {
            "skill_name": "Boundary Maintenance",
            "score": 90,
            "feedback": "Detailed feedback here",
            "strengths": ["Professional boundaries maintained"],
            "areas_for_improvement": ["Continue current approach"]
        },
        "crisis_management": {
            "skill_name": "Crisis Management",
            "score": 85,
            "feedback": "Detailed feedback here",
            "strengths": ["Appropriate response to distress"],
            "areas_for_improvement": ["Practice de-escalation techniques"]
        },
        "therapeutic_interventions": {
            "skill_name": "Therapeutic Interventions",
            "score": 80,
            "feedback": "Detailed feedback here",
            "strengths": ["Used appropriate techniques"],
            "areas_for_improvement": ["Expand intervention repertoire"]
        },
        "silence_management": "Good",
        "session_structure": "Good", 
        "hipaa_compliance": true,
        "ethical_boundaries": true,
        "professional_language": true,
        "immediate_feedback": ["Specific feedback point 1", "Specific feedback point 2"],
        "long_term_development": ["Development goal 1", "Development goal 2"],
        "recommended_resources": ["Resource 1", "Resource 2"],
        "risk_flags": [],
        "supervisor_review_required": false
    }
    
    Be STRICT in scoring - this is professional training evaluation.
    Return ONLY valid JSON without markdown formatting.
    """
    
    try:
        logger.info(f"🤖 Sending analysis request to OpenAI GPT-4o-mini")
        
        # Get AI analysis with timeout
        response = await asyncio.wait_for(
            openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert clinical supervisor providing HIPAA-compliant therapy session evaluation. Respond only with valid JSON matching the SessionInsights schema. Be strict in scoring - this is professional training."
                    },
                    {
                        "role": "user", 
                        "content": analysis_prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent scoring
                max_tokens=4000
            ),
            timeout=30.0  # 30 second timeout
        )
        
        logger.info(f"✅ Received response from OpenAI")
        
        # Parse AI response
        raw_content = response.choices[0].message.content
        logger.info(f"📝 Parsing AI response (length: {len(raw_content)} chars)")
        
        # Clean up the response - remove markdown code blocks if present
        cleaned_content = raw_content.strip()
        if cleaned_content.startswith('```json'):
            cleaned_content = cleaned_content[7:]  # Remove ```json
        if cleaned_content.startswith('```'):
            cleaned_content = cleaned_content[3:]   # Remove ```
        if cleaned_content.endswith('```'):
            cleaned_content = cleaned_content[:-3]  # Remove trailing ```
        cleaned_content = cleaned_content.strip()
        
        logger.info(f"📝 Cleaned content for parsing: {cleaned_content[:200]}...")
        
        ai_analysis = json.loads(cleaned_content)
        
        # Validate and create insights object
        insights = SessionInsights(
            overall_score=ai_analysis.get("overall_score", 0),
            grade=calculate_grade(ai_analysis.get("overall_score", 0)),
            session_summary=ai_analysis.get("session_summary", ""),
            patient_engagement_level=ai_analysis.get("patient_engagement_level", "Moderate"),
            therapeutic_rapport=ai_analysis.get("therapeutic_rapport", "Fair"),
            
            # Skill scores
            active_listening=TherapySkillScore(**ai_analysis.get("active_listening", {
                "skill_name": "Active Listening",
                "score": 0,
                "feedback": "No assessment available",
                "strengths": [],
                "areas_for_improvement": ["Complete session analysis needed"]
            })),
            empathy_demonstration=TherapySkillScore(**ai_analysis.get("empathy_demonstration", {
                "skill_name": "Empathy Demonstration",
                "score": 0,
                "feedback": "No assessment available",
                "strengths": [],
                "areas_for_improvement": ["Complete session analysis needed"]
            })),
            questioning_techniques=TherapySkillScore(**ai_analysis.get("questioning_techniques", {
                "skill_name": "Questioning Techniques",
                "score": 0,
                "feedback": "No assessment available",
                "strengths": [],
                "areas_for_improvement": ["Complete session analysis needed"]
            })),
            boundary_maintenance=TherapySkillScore(**ai_analysis.get("boundary_maintenance", {
                "skill_name": "Boundary Maintenance",
                "score": 0,
                "feedback": "No assessment available",
                "strengths": [],
                "areas_for_improvement": ["Complete session analysis needed"]
            })),
            crisis_management=TherapySkillScore(**ai_analysis.get("crisis_management", {
                "skill_name": "Crisis Management",
                "score": 0,
                "feedback": "No assessment available",
                "strengths": [],
                "areas_for_improvement": ["Complete session analysis needed"]
            })),
            therapeutic_interventions=TherapySkillScore(**ai_analysis.get("therapeutic_interventions", {
                "skill_name": "Therapeutic Interventions",
                "score": 0,
                "feedback": "No assessment available",
                "strengths": [],
                "areas_for_improvement": ["Complete session analysis needed"]
            })),
            
            # Session metrics
            student_talk_percentage=student_talk_pct,
            patient_talk_percentage=patient_talk_pct,
            silence_management=ai_analysis.get("silence_management", "Fair"),
            session_structure=ai_analysis.get("session_structure", "Fair"),
            
            # Compliance
            hipaa_compliance=ai_analysis.get("hipaa_compliance", True),
            ethical_boundaries=ai_analysis.get("ethical_boundaries", True),
            professional_language=ai_analysis.get("professional_language", True),
            
            # Recommendations
            immediate_feedback=ai_analysis.get("immediate_feedback", []),
            long_term_development=ai_analysis.get("long_term_development", []),
            recommended_resources=ai_analysis.get("recommended_resources", []),
            
            # Risk assessment
            risk_flags=ai_analysis.get("risk_flags", []),
            supervisor_review_required=ai_analysis.get("supervisor_review_required", False)
        )
        
        logger.info(f"Generated insights with overall score: {insights.overall_score} ({insights.grade})")
        return insights
        
    except asyncio.TimeoutError:
        logger.error(f"⏰ OpenAI API request timed out after 30 seconds")
        return _create_default_insights(student_talk_pct, patient_talk_pct, duration)
    
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse AI analysis JSON: {e}")
        logger.error(f"Raw AI response: {raw_content[:500]}...")
        # Return default insights on parsing failure
        return _create_default_insights(student_talk_pct, patient_talk_pct, duration)
    
    except Exception as e:
        logger.error(f"❌ Error generating session insights: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        # Return default insights on any error
        return _create_default_insights(student_talk_pct, patient_talk_pct, duration)

def _create_default_insights(student_talk_pct: float, patient_talk_pct: float, duration: int) -> SessionInsights:
    """Create default insights when AI analysis fails"""
    
    # Basic scoring based on talk time and duration
    base_score = 60
    
    # Adjust for talk time ratios
    if 30 <= student_talk_pct <= 40:
        base_score += 10
    elif student_talk_pct > 50:
        base_score -= 15
    elif student_talk_pct < 20:
        base_score -= 10
    
    # Adjust for session duration
    if duration >= 600:  # 10+ minutes
        base_score += 5
    elif duration < 300:  # Less than 5 minutes
        base_score -= 10
    
    base_score = max(0, min(100, base_score))
    
    default_skill = TherapySkillScore(
        skill_name="Default Assessment",
        score=base_score,
        feedback="Automated assessment - manual review recommended",
        strengths=["Completed session"],
        areas_for_improvement=["Detailed analysis needed"]
    )
    
    return SessionInsights(
        overall_score=base_score,
        grade=calculate_grade(base_score),
        session_summary="Session completed - detailed analysis unavailable",
        patient_engagement_level="Moderate",
        therapeutic_rapport="Fair",
        
        active_listening=default_skill,
        empathy_demonstration=default_skill,
        questioning_techniques=default_skill,
        boundary_maintenance=default_skill,
        crisis_management=default_skill,
        therapeutic_interventions=default_skill,
        
        student_talk_percentage=student_talk_pct,
        patient_talk_percentage=patient_talk_pct,
        silence_management="Fair",
        session_structure="Fair",
        
        hipaa_compliance=True,
        ethical_boundaries=True,
        professional_language=True,
        
        immediate_feedback=["Complete detailed session review"],
        long_term_development=["Continue practicing therapy skills"],
        recommended_resources=["Therapy training materials"],
        
        risk_flags=[],
        supervisor_review_required=True
    )