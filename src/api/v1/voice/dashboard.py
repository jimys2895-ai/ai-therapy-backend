from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from ....database import (
    get_sessions_collection, get_patients_collection, 
    get_users_collection, get_settings_collection
)
from ....models.dashboard import (
    DashboardStats, StudentOverview, AdminDashboardStats,
    StudentSessionSummary, DetailedSessionAnalysis, ConversationMessage,
    PlatformAnalytics, RecentActivity, StudentPerformanceMetrics,
    SessionDistribution, ScoreDistribution, DashboardFilter, ExportRequest
)
from ....models.history import SessionStatus
from ....auth.dependencies import get_current_user
from ....models.users import User

router = APIRouter()

def _ensure_utc(dt) -> datetime:
    """Normalize any datetime to UTC-aware, handling None and naive datetimes."""
    if not isinstance(dt, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# Helper function to get patient name by ID
async def get_patient_name_by_id(patient_id: str, patients_collection) -> str:
    """
    Get patient name by ID, handling both string and ObjectId formats
    """
    if not patient_id:
        return "Unknown Patient"
    
    try:
        # First try with string ID
        patient = await patients_collection.find_one({"_id": patient_id})
        if patient:
            return patient.get("name", "Unknown Patient")
        
        # Then try with ObjectId conversion
        try:
            patient = await patients_collection.find_one({"_id": ObjectId(patient_id)})
            if patient:
                return patient.get("name", "Unknown Patient")
        except:
            pass
            
        return "Unknown Patient"
    except Exception as e:
        print(f"Error getting patient name for ID {patient_id}: {e}")
        return "Unknown Patient"

async def get_patient_names_by_ids(patient_ids: List[str], patients_collection) -> Dict[str, str]:
    """
    Get patient names for multiple IDs efficiently
    """
    if not patient_ids:
        return {}
    
    patient_names = {}
    
    try:
        # First try with string IDs
        patients_cursor = patients_collection.find({"_id": {"$in": patient_ids}})
        patients_by_string = await patients_cursor.to_list(length=None)
        for patient in patients_by_string:
            patient_names[str(patient["_id"])] = patient.get("name", "Unknown Patient")
        
        # Then try with ObjectId conversion for any remaining
        remaining_ids = [pid for pid in patient_ids if str(pid) not in patient_names]
        if remaining_ids:
            patient_object_ids = []
            for pid in remaining_ids:
                try:
                    patient_object_ids.append(ObjectId(pid))
                except:
                    continue
            
            if patient_object_ids:
                patients_cursor = patients_collection.find({"_id": {"$in": patient_object_ids}})
                patients_by_objectid = await patients_cursor.to_list(length=None)
                for patient in patients_by_objectid:
                    patient_names[str(patient["_id"])] = patient.get("name", "Unknown Patient")
        
        # Fill in any missing names
        for pid in patient_ids:
            if str(pid) not in patient_names:
                patient_names[str(pid)] = "Unknown Patient"
                
        print(f"Patient names lookup: {patient_names}")
        return patient_names
        
    except Exception as e:
        print(f"Error getting patient names: {e}")
        return {str(pid): "Unknown Patient" for pid in patient_ids}

# Response models for OpenAPI documentation
class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message")

class StudentDashboardResponse(BaseModel):
    stats: DashboardStats = Field(..., description="Student dashboard statistics")
    recent_sessions: List[StudentSessionSummary] = Field(..., description="Recent session summaries")

class AdminDashboardResponse(BaseModel):
    stats: AdminDashboardStats = Field(..., description="Admin dashboard statistics")
    students: List[StudentOverview] = Field(..., description="Student overviews")
    recent_activity: List[RecentActivity] = Field(..., description="Recent platform activity")


@router.get("/student",
    response_model=StudentDashboardResponse,
    summary="Get student dashboard data",
    description="Retrieve comprehensive dashboard data for the current student",
    responses={
        200: {
            "description": "Student dashboard data retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "stats": {
                            "total_sessions": 12,
                            "average_score": 87.5,
                            "hours_completed": 24.0,
                            "current_streak": 5,
                            "sessions_this_week": 3,
                            "sessions_this_month": 12,
                            "improvement_trend": 15.2,
                            "active_today": 1
                        },
                        "recent_sessions": [
                            {
                                "session_id": "507f1f77bcf86cd799439011",
                                "patient_name": "Sarah Johnson",
                                "patient_id": "507f1f77bcf86cd799439012",
                                "duration": 2700,
                                "score": 87,
                                "date": "2024-01-21T14:30:00Z",
                                "feedback": "Excellent session! Strong empathy demonstrated.",
                                "status": "completed"
                            }
                        ]
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve dashboard data"}
    }
)
async def get_student_dashboard(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive dashboard data for the current student.
    
    Returns:
    - Personal performance statistics
    - Recent session summaries
    - Progress tracking metrics
    - Learning streak information
    """
    try:
        sessions_collection = get_sessions_collection()
        patients_collection = get_patients_collection()
        
        # Get all sessions for the student
        all_sessions = await sessions_collection.find({
            "student_id": current_user.id
        }).to_list(length=None)
        
        completed_sessions = [s for s in all_sessions if s.get("status") == SessionStatus.COMPLETED]
        
        # Calculate basic stats
        total_sessions = len(completed_sessions)
        total_duration = sum(session.get("duration", 0) for session in completed_sessions)
        hours_completed = total_duration / 3600 if total_duration > 0 else 0.0
        
        # Calculate average score
        scores = [session.get("score", 0) for session in completed_sessions if session.get("score")]
        average_score = sum(scores) / len(scores) if scores else 0.0
        
        # Calculate time-based metrics
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sessions_this_week = len([
            s for s in completed_sessions
            if _ensure_utc(s.get("start_time")) >= week_ago
        ])

        sessions_this_month = len([
            s for s in completed_sessions
            if _ensure_utc(s.get("start_time")) >= month_ago
        ])

        active_today = len([
            s for s in completed_sessions
            if _ensure_utc(s.get("start_time")) >= today_start
        ])

        # Calculate current streak
        current_streak = 0
        sessions_by_date = {}
        for session in completed_sessions:
            date = _ensure_utc(session.get("start_time")).date()
            sessions_by_date[date] = sessions_by_date.get(date, 0) + 1
        
        current_date = now.date()
        while current_date in sessions_by_date:
            current_streak += 1
            current_date -= timedelta(days=1)
        
        # Calculate improvement trend
        improvement_trend = 0.0
        if len(scores) >= 2:
            recent_scores = scores[-5:] if len(scores) >= 5 else scores[-len(scores)//2:]
            early_scores = scores[:5] if len(scores) >= 5 else scores[:len(scores)//2]
            if early_scores and recent_scores:
                recent_avg = sum(recent_scores) / len(recent_scores)
                early_avg = sum(early_scores) / len(early_scores)
                improvement_trend = ((recent_avg - early_avg) / early_avg) * 100 if early_avg > 0 else 0.0
        
        # Create stats object
        stats = DashboardStats(
            total_sessions=total_sessions,
            average_score=round(average_score, 1),
            hours_completed=round(hours_completed, 1),
            current_streak=current_streak,
            sessions_this_week=sessions_this_week,
            sessions_this_month=sessions_this_month,
            improvement_trend=round(improvement_trend, 1),
            active_today=active_today
        )
        
        # Get recent sessions with patient names
        recent_sessions_data = sorted(completed_sessions, key=lambda x: _ensure_utc(x.get("start_time")), reverse=True)[:10]
        
        # Get patient names using helper function
        patient_ids = list(set([s.get("patient_id") for s in recent_sessions_data if s.get("patient_id")]))
        patient_names = await get_patient_names_by_ids(patient_ids, patients_collection)
        
        # Create recent sessions summaries
        recent_sessions = []
        for session in recent_sessions_data:
            patient_name = patient_names.get(str(session.get("patient_id", "")), "Unknown Patient")
            
            # Get transcript messages
            transcript_data = session.get("transcript", [])
            transcript_messages = []
            for msg in transcript_data:
                # Convert timestamp to string if it's a datetime object
                timestamp = msg.get("timestamp", "")
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                elif timestamp and not isinstance(timestamp, str):
                    timestamp = str(timestamp)
                
                transcript_messages.append(ConversationMessage(
                    id=msg.get("id", ""),
                    speaker=msg.get("speaker", "student"),
                    text=msg.get("text", ""),
                    timestamp=timestamp,
                    emotion=msg.get("emotion")
                ))
            
            recent_sessions.append(StudentSessionSummary(
                session_id=str(session["_id"]),
                patient_name=patient_name,
                patient_id=session.get("patient_id", ""),
                duration=session.get("duration", 0),
                score=session.get("score"),
                date=_ensure_utc(session.get("start_time")),
                feedback=session.get("feedback"),
                status=session.get("status", "unknown"),
                transcript=transcript_messages,
                message_count=len(transcript_data),
                
                # Add full session insights and metadata
                insights=session.get("insights"),
                insights_generated=session.get("insights_generated"),
                analysis=session.get("analysis"),
                performance_metrics=session.get("performance_metrics"),
                session_notes=session.get("session_notes"),
                audio_file_id=session.get("audio_file_id"),
                audio_enabled=session.get("audio_enabled"),
                voice_type=session.get("voice_type"),
                voice_speed=session.get("voice_speed"),
                start_time=session.get("start_time"),
                end_time=session.get("end_time"),
                created_at=session.get("created_at"),
                updated_at=session.get("updated_at")
            ))
        
        return StudentDashboardResponse(
            stats=stats,
            recent_sessions=recent_sessions
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve student dashboard data: {str(e)}"
        )


@router.get("/admin",
    response_model=AdminDashboardResponse,
    summary="Get admin dashboard data",
    description="Retrieve comprehensive dashboard data for administrators",
    responses={
        200: {
            "description": "Admin dashboard data retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "stats": {
                            "total_students": 25,
                            "total_sessions": 150,
                            "average_score": 85.2,
                            "active_today": 8,
                            "active_this_week": 20,
                            "active_this_month": 25,
                            "total_hours": 300.5,
                            "completion_rate": 92.5
                        },
                        "students": [
                            {
                                "id": "507f1f77bcf86cd799439011",
                                "name": "Alice Johnson",
                                "email": "alice@stanford.edu",
                                "university": "Stanford University",
                                "year": 3,
                                "total_sessions": 15,
                                "average_score": 92.0,
                                "last_active": "2024-01-21T14:30:00Z",
                                "created_at": "2024-01-01T10:00:00Z"
                            }
                        ],
                        "recent_activity": [
                            {
                                "student_id": "507f1f77bcf86cd799439011",
                                "student_name": "Alice Johnson",
                                "activity_type": "session_completed",
                                "description": "Completed session with Sarah Johnson",
                                "timestamp": "2024-01-21T14:30:00Z"
                            }
                        ]
                    }
                }
            }
        },
        403: {"description": "Admin access required"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve admin dashboard data"}
    }
)
async def get_admin_dashboard(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive dashboard data for administrators.
    
    Requires admin role. Returns:
    - Platform-wide statistics
    - Student overviews and performance
    - Recent platform activity
    - Usage analytics
    """
    try:
        # Check admin permissions
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        sessions_collection = get_sessions_collection()
        users_collection = get_users_collection()
        patients_collection = get_patients_collection()
        
        # Get all students (users with role 'student')
        students_cursor = users_collection.find({"role": "student"})
        students = await students_cursor.to_list(length=None)
        
        # Get all sessions
        all_sessions = await sessions_collection.find({}).to_list(length=None)
        completed_sessions = [s for s in all_sessions if s.get("status") == SessionStatus.COMPLETED]
        
        # Calculate platform stats
        total_students = len(students)
        total_sessions = len(completed_sessions)
        
        # Calculate average score across all sessions
        all_scores = [s.get("score", 0) for s in completed_sessions if s.get("score")]
        average_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
        
        # Calculate time-based activity
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # Sessions today (count of sessions today)
        sessions_today = len([s for s in completed_sessions if _ensure_utc(s.get("start_time")) >= today_start])

        # Students active this week
        active_week_sessions = [s for s in completed_sessions if _ensure_utc(s.get("start_time")) >= week_ago]
        active_week_student_ids = set([str(s.get("student_id")) for s in active_week_sessions if s.get("student_id")])
        active_this_week = len(active_week_student_ids)

        # Students active this month
        active_month_sessions = [s for s in completed_sessions if _ensure_utc(s.get("start_time")) >= month_ago]
        active_month_student_ids = set([str(s.get("student_id")) for s in active_month_sessions if s.get("student_id")])
        active_this_month = len(active_month_student_ids)
        
        # Calculate total hours
        total_duration = sum(s.get("duration", 0) for s in completed_sessions)
        total_hours = total_duration / 3600 if total_duration > 0 else 0.0
        
        # Calculate completion rate (completed vs all sessions)
        completion_rate = (len(completed_sessions) / len(all_sessions)) * 100 if all_sessions else 0.0
        
        # Get pending requests count
        from ....services.account_status import AccountStatusManager
        pending_requests = await AccountStatusManager.get_pending_requests_count()
        
        # Create admin stats
        admin_stats = AdminDashboardStats(
            total_students=total_students,
            total_sessions=total_sessions,
            average_score=round(average_score, 1),
            active_today=sessions_today,
            active_this_week=active_this_week,
            active_this_month=active_this_month,
            total_hours=round(total_hours, 1),
            completion_rate=round(completion_rate, 1),
            pending_requests=pending_requests
        )
        
        # Create student overviews
        student_overviews = []
        for student in students:
            student_id_str = str(student["_id"])
            student_sessions = [s for s in completed_sessions if str(s.get("student_id")) == student_id_str]
            student_scores = [s.get("score", 0) for s in student_sessions if s.get("score") is not None]
            
            # Find last active session
            last_session = max(student_sessions, key=lambda x: _ensure_utc(x.get("start_time")), default=None)
            last_active = _ensure_utc(last_session.get("start_time") if last_session else student.get("created_at"))
            
            student_overviews.append(StudentOverview(
                _id=student_id_str,
                name=student.get("name", "Unknown"),
                email=student.get("email", ""),
                university=student.get("university"),
                year=student.get("year"),
                total_sessions=len(student_sessions),
                average_score=round(sum(student_scores) / len(student_scores), 1) if student_scores else 0.0,
                last_active=last_active,
                created_at=_ensure_utc(student.get("created_at"))
            ))
        
        # Sort students by last active (most recent first)
        student_overviews.sort(key=lambda x: _ensure_utc(x.last_active), reverse=True)
        
        # Create recent activity (mock data based on recent sessions)
        recent_activity = []
        recent_sessions = sorted(completed_sessions, key=lambda x: _ensure_utc(x.get("start_time")), reverse=True)[:10]
        
        # Get patient names for activity descriptions using helper function
        patient_ids = list(set([s.get("patient_id") for s in recent_sessions if s.get("patient_id")]))
        patient_names = await get_patient_names_by_ids(patient_ids, patients_collection)
        
        # Create student name lookup
        student_names = {str(s["_id"]): s.get("name", "Unknown") for s in students}
        
        for session in recent_sessions:
            student_id_str = str(session.get("student_id", ""))
            student_name = student_names.get(student_id_str, "Unknown Student")
            patient_name = patient_names.get(str(session.get("patient_id", "")), "Unknown Patient")
            
            recent_activity.append(RecentActivity(
                student_id=student_id_str,
                student_name=student_name,
                activity_type="session_completed",
                description=f"Completed session with {patient_name}",
                timestamp=_ensure_utc(session.get("start_time")),
                metadata={
                    "session_id": str(session["_id"]),
                    "patient_id": session.get("patient_id"),
                    "score": session.get("score"),
                    "duration": session.get("duration")
                }
            ))
        
        return AdminDashboardResponse(
            stats=admin_stats,
            students=student_overviews,
            recent_activity=recent_activity
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve admin dashboard data: {str(e)}"
        )


@router.get("/admin/students/{student_id}/sessions",
    response_model=List[StudentSessionSummary],
    summary="Get student sessions",
    description="Get all sessions for a specific student (admin only)",
    responses={
        200: {"description": "Student sessions retrieved successfully"},
        403: {"description": "Admin access required"},
        404: {"description": "Student not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve student sessions"}
    }
)
async def get_student_sessions(
    student_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all sessions for a specific student (admin only).
    
    Returns detailed session information including:
    - Session performance scores
    - Patient interaction summaries
    - AI-generated feedback
    - Session duration and timing
    """
    try:
        # Check admin permissions
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        sessions_collection = get_sessions_collection()
        patients_collection = get_patients_collection()
        users_collection = get_users_collection()
        
        # Verify student exists
        student = await users_collection.find_one({"_id": ObjectId(student_id)})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        # Get all sessions for the student
        student_sessions = await sessions_collection.find({
            "student_id": student_id
        }).to_list(length=None)
        
        # Get patient names using helper function
        patient_ids = list(set([s.get("patient_id") for s in student_sessions if s.get("patient_id")]))
        patient_names = await get_patient_names_by_ids(patient_ids, patients_collection)
        
        # Create session summaries
        session_summaries = []
        for session in student_sessions:
            patient_name = patient_names.get(str(session.get("patient_id", "")), "Unknown Patient")
            
            # Debug: Log session data structure
            print(f"Processing session {session.get('_id')}: has insights = {bool(session.get('insights'))}")
            if session.get('insights'):
                print(f"Insights keys: {list(session.get('insights', {}).keys())}")
            
            # Get transcript messages
            transcript_data = session.get("transcript", [])
            transcript_messages = []
            for msg in transcript_data:
                # Convert timestamp to string if it's a datetime object
                timestamp = msg.get("timestamp", "")
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                elif timestamp and not isinstance(timestamp, str):
                    timestamp = str(timestamp)
                
                transcript_messages.append(ConversationMessage(
                    id=msg.get("id", ""),
                    speaker=msg.get("speaker", "student"),
                    text=msg.get("text", ""),
                    timestamp=timestamp,
                    emotion=msg.get("emotion")
                ))
            
            session_summaries.append(StudentSessionSummary(
                session_id=str(session["_id"]),
                patient_name=patient_name,
                patient_id=session.get("patient_id", ""),
                duration=session.get("duration", 0),
                score=session.get("score"),
                date=_ensure_utc(session.get("start_time")),
                feedback=session.get("feedback"),
                status=session.get("status", "unknown"),
                transcript=transcript_messages,
                message_count=len(transcript_data),
                
                # Add full session insights and metadata
                insights=session.get("insights"),
                insights_generated=session.get("insights_generated"),
                analysis=session.get("analysis"),
                performance_metrics=session.get("performance_metrics"),
                session_notes=session.get("session_notes"),
                audio_file_id=session.get("audio_file_id"),
                audio_enabled=session.get("audio_enabled"),
                voice_type=session.get("voice_type"),
                voice_speed=session.get("voice_speed"),
                start_time=session.get("start_time"),
                end_time=session.get("end_time"),
                created_at=session.get("created_at"),
                updated_at=session.get("updated_at")
            ))
        
        # Sort by date (most recent first)
        session_summaries.sort(key=lambda x: x.date, reverse=True)
        
        return session_summaries
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve student sessions: {str(e)}"
        )


@router.get("/admin/analytics",
    response_model=PlatformAnalytics,
    summary="Get platform analytics",
    description="Get comprehensive platform analytics (admin only)",
    responses={
        200: {"description": "Platform analytics retrieved successfully"},
        403: {"description": "Admin access required"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve platform analytics"}
    }
)
async def get_platform_analytics(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive platform analytics (admin only).
    
    Returns detailed analytics including:
    - User engagement metrics
    - Session completion trends
    - Performance distributions
    - Popular patient personas
    - Usage patterns and insights
    """
    try:
        # Check admin permissions
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        sessions_collection = get_sessions_collection()
        users_collection = get_users_collection()
        patients_collection = get_patients_collection()
        
        # Get all data
        all_sessions = await sessions_collection.find({}).to_list(length=None)
        all_students = await users_collection.find({"role": "student"}).to_list(length=None)
        all_patients = await patients_collection.find({}).to_list(length=None)
        
        completed_sessions = [s for s in all_sessions if s.get("status") == SessionStatus.COMPLETED]
        
        # Calculate user engagement
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        weekly_active = len(set([s.get("student_id") for s in completed_sessions if _ensure_utc(s.get("start_time")) >= week_ago]))
        monthly_active = len(set([s.get("student_id") for s in completed_sessions if _ensure_utc(s.get("start_time")) >= month_ago]))
        
        user_engagement = {
            "total_users": len(all_students),
            "weekly_active_users": weekly_active,
            "monthly_active_users": monthly_active,
            "engagement_rate": round((weekly_active / len(all_students)) * 100, 1) if all_students else 0.0
        }
        
        # Calculate session trends (last 30 days)
        daily_sessions = {}
        for i in range(30):
            date = (now - timedelta(days=i)).date()
            daily_sessions[date.isoformat()] = 0
        
        for session in completed_sessions:
            session_date = _ensure_utc(session.get("start_time")).date()
            if session_date.isoformat() in daily_sessions:
                daily_sessions[session_date.isoformat()] += 1
        
        session_trends = {
            "daily_sessions": daily_sessions,
            "total_sessions": len(completed_sessions),
            "completion_rate": round((len(completed_sessions) / len(all_sessions)) * 100, 1) if all_sessions else 0.0
        }
        
        # Calculate performance metrics
        all_scores = [s.get("score", 0) for s in completed_sessions if s.get("score")]
        performance_metrics = {
            "average_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0,
            "score_distribution": {
                "excellent": len([s for s in all_scores if s >= 90]),
                "good": len([s for s in all_scores if 80 <= s < 90]),
                "fair": len([s for s in all_scores if 70 <= s < 80]),
                "needs_improvement": len([s for s in all_scores if s < 70])
            }
        }
        
        # Calculate popular patients
        patient_usage = {}
        for session in completed_sessions:
            patient_id = session.get("patient_id")
            if patient_id:
                patient_usage[patient_id] = patient_usage.get(patient_id, 0) + 1
        
        # Get patient names - ensure proper string conversion
        patient_names = {str(p["_id"]): p["name"] for p in all_patients}
        
        popular_patients = []
        for patient_id, count in sorted(patient_usage.items(), key=lambda x: x[1], reverse=True)[:5]:
            popular_patients.append({
                "patient_id": patient_id,
                "patient_name": patient_names.get(patient_id, "Unknown"),
                "session_count": count,
                "popularity_percentage": round((count / len(completed_sessions)) * 100, 1)
            })
        
        # Calculate usage patterns
        hourly_usage = {}
        for i in range(24):
            hourly_usage[str(i)] = 0
        
        for session in completed_sessions:
            hour = _ensure_utc(session.get("start_time")).hour
            hourly_usage[str(hour)] += 1
        
        usage_patterns = {
            "hourly_distribution": hourly_usage,
            "peak_hour": max(hourly_usage.items(), key=lambda x: x[1])[0] if hourly_usage else "0",
            "average_session_duration": round(sum([s.get("duration", 0) for s in completed_sessions]) / len(completed_sessions) / 60, 1) if completed_sessions else 0.0
        }
        
        return PlatformAnalytics(
            user_engagement=user_engagement,
            session_trends=session_trends,
            performance_metrics=performance_metrics,
            popular_patients=popular_patients,
            usage_patterns=usage_patterns
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve platform analytics: {str(e)}"
        )


@router.get("/admin/sessions",
    response_model=List[StudentSessionSummary],
    summary="Get all sessions (admin only)",
    description="Get all sessions across all students for admin analysis",
    responses={
        200: {"description": "All sessions retrieved successfully"},
        403: {"description": "Admin access required"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve sessions"}
    }
)
async def get_all_sessions_admin(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip for pagination"),
    student_id: Optional[str] = Query(None, description="Filter by specific student ID"),
    current_user: User = Depends(get_current_user)
):
    """
    Get all sessions across all students (admin only).
    
    Returns detailed session information for administrative analysis including:
    - All student sessions with performance data
    - Patient interaction summaries
    - Session scores and feedback
    - Comprehensive session metadata
    """
    try:
        # Check admin permissions
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        sessions_collection = get_sessions_collection()
        patients_collection = get_patients_collection()
        users_collection = get_users_collection()
        
        # Build filter query
        filter_query = {}
        if student_id:
            filter_query["student_id"] = student_id
        
        # Get sessions with pagination, sorted by most recent first
        all_sessions = await sessions_collection.find(filter_query).sort("start_time", -1).skip(offset).limit(limit).to_list(length=None)
        
        if not all_sessions:
            return []
        
        # Get patient names using helper function
        patient_ids = list(set([s.get("patient_id") for s in all_sessions if s.get("patient_id")]))
        patient_names = await get_patient_names_by_ids(patient_ids, patients_collection)
        
        # Create session summaries
        session_summaries = []
        for session in all_sessions:
            patient_name = patient_names.get(str(session.get("patient_id", "")), "Unknown Patient")
            
            # Get transcript messages
            transcript_data = session.get("transcript", [])
            transcript_messages = []
            for msg in transcript_data:
                # Convert timestamp to string if it's a datetime object
                timestamp = msg.get("timestamp", "")
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                elif timestamp and not isinstance(timestamp, str):
                    timestamp = str(timestamp)
                
                transcript_messages.append(ConversationMessage(
                    id=msg.get("id", ""),
                    speaker=msg.get("speaker", "student"),
                    text=msg.get("text", ""),
                    timestamp=timestamp,
                    emotion=msg.get("emotion")
                ))
            
            session_summaries.append(StudentSessionSummary(
                session_id=str(session["_id"]),
                patient_name=patient_name,
                patient_id=session.get("patient_id", ""),
                duration=session.get("duration", 0),
                score=session.get("score"),
                date=_ensure_utc(session.get("start_time")),
                feedback=session.get("feedback"),
                status=session.get("status", "unknown"),
                transcript=transcript_messages,
                message_count=len(transcript_data),
                
                # Add full session insights and metadata
                insights=session.get("insights"),
                insights_generated=session.get("insights_generated"),
                analysis=session.get("analysis"),
                performance_metrics=session.get("performance_metrics"),
                session_notes=session.get("session_notes"),
                audio_file_id=session.get("audio_file_id"),
                audio_enabled=session.get("audio_enabled"),
                voice_type=session.get("voice_type"),
                voice_speed=session.get("voice_speed"),
                start_time=session.get("start_time"),
                end_time=session.get("end_time"),
                created_at=session.get("created_at"),
                updated_at=session.get("updated_at")
            ))
        
        return session_summaries
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve all sessions: {str(e)}"
        )