from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from bson import ObjectId
from datetime import datetime


class DashboardStats(BaseModel):
    total_sessions: int
    average_score: float
    hours_completed: float
    current_streak: int
    sessions_this_week: int
    sessions_this_month: int
    improvement_trend: float
    active_today: int


class StudentOverview(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: str
    university: Optional[str] = None
    year: Optional[int] = None
    total_sessions: int
    average_score: float
    last_active: datetime
    created_at: datetime
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class AdminDashboardStats(BaseModel):
    total_students: int
    total_sessions: int
    average_score: float
    active_today: int  # This represents sessions today, not unique active users
    active_this_week: int
    active_this_month: int
    total_hours: float
    completion_rate: float
    pending_requests: int  # Number of users with 'requested' status


class ConversationMessage(BaseModel):
    id: str
    speaker: str  # 'student' or 'patient'
    text: str
    timestamp: str
    emotion: Optional[str] = None


class StudentSessionSummary(BaseModel):
    session_id: str
    patient_name: str
    patient_id: str
    duration: int
    score: Optional[int] = None
    date: datetime
    feedback: Optional[str] = None
    status: str
    transcript: Optional[List[ConversationMessage]] = None
    message_count: Optional[int] = None
    
    # Add full session insights support
    insights: Optional[Dict[str, Any]] = None  # Will contain SessionInsights data
    insights_generated: Optional[bool] = None
    
    # Legacy fields for backward compatibility
    analysis: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    session_notes: Optional[str] = None
    audio_file_id: Optional[str] = None
    audio_enabled: Optional[bool] = None
    voice_type: Optional[str] = None
    voice_speed: Optional[float] = None
    
    # Session timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DetailedSessionAnalysis(BaseModel):
    session_id: str
    patient_name: str
    duration: int
    score: int
    date: datetime
    feedback: str
    conversation: List[ConversationMessage]
    skill_assessment: Dict[str, int]
    strengths: List[str]
    improvements: List[str]
    detailed_analysis: Dict[str, str]
    recommendations: List[str]


class PlatformAnalytics(BaseModel):
    user_engagement: Dict[str, Any]
    session_trends: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    popular_patients: List[Dict[str, Any]]
    usage_patterns: Dict[str, Any]


class RecentActivity(BaseModel):
    student_id: str
    student_name: str
    activity_type: str  # 'session_completed', 'login', 'profile_updated'
    description: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class StudentPerformanceMetrics(BaseModel):
    student_id: str
    student_name: str
    total_sessions: int
    average_score: float
    hours_completed: float
    improvement_trend: float
    last_session_date: Optional[datetime] = None
    strengths: List[str]
    areas_for_improvement: List[str]
    recommended_patients: List[str]


class SessionDistribution(BaseModel):
    beginner: int
    intermediate: int
    advanced: int


class ScoreDistribution(BaseModel):
    excellent: int  # 90-100
    good: int      # 80-89
    fair: int      # 70-79
    needs_improvement: int  # <70


class DashboardFilter(BaseModel):
    date_range: Optional[str] = None  # 'today', 'week', 'month', 'all'
    student_ids: Optional[List[str]] = None
    patient_ids: Optional[List[str]] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    difficulty_levels: Optional[List[str]] = None


class ExportRequest(BaseModel):
    export_type: str  # 'sessions', 'students', 'analytics'
    format: str = 'csv'  # 'csv', 'xlsx', 'pdf'
    filters: Optional[DashboardFilter] = None
    include_transcripts: bool = False
    date_range: Optional[Dict[str, datetime]] = None