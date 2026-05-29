from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from bson import ObjectId
from datetime import datetime


class MessageSpeaker(str, Enum):
    STUDENT = "student"
    PATIENT = "patient"


class TranscriptMessage(BaseModel):
    id: str
    speaker: MessageSpeaker
    text: str
    timestamp: datetime
    audio_url: Optional[str] = None


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TherapySkillScore(BaseModel):
    """Individual therapy skill scoring"""
    skill_name: str
    score: int  # 0-100
    feedback: str
    strengths: List[str]
    areas_for_improvement: List[str]


class SessionInsights(BaseModel):
    """Complete session analysis and insights"""
    overall_score: int  # 0-100
    grade: str  # A+, A, A-, B+, B, B-, C+, C, C-, D+, D, F
    session_summary: str
    patient_engagement_level: str  # Low, Moderate, High
    therapeutic_rapport: str  # Poor, Fair, Good, Excellent
    
    # Detailed skill assessments
    active_listening: TherapySkillScore
    empathy_demonstration: TherapySkillScore
    questioning_techniques: TherapySkillScore
    boundary_maintenance: TherapySkillScore
    crisis_management: TherapySkillScore
    therapeutic_interventions: TherapySkillScore
    
    # Session metrics
    student_talk_percentage: float
    patient_talk_percentage: float
    silence_management: str  # Poor, Fair, Good, Excellent
    session_structure: str  # Poor, Fair, Good, Excellent
    
    # Compliance and ethics
    hipaa_compliance: bool
    ethical_boundaries: bool
    professional_language: bool
    
    # Recommendations
    immediate_feedback: List[str]
    long_term_development: List[str]
    recommended_resources: List[str]
    
    # Risk assessment
    risk_flags: List[str]
    supervisor_review_required: bool
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    id: str = Field(alias="_id")
    student_id: str  # Reference to User
    patient_id: str  # Reference to Patient
    start_time: datetime
    end_time: Optional[datetime] = None
    transcript: List[TranscriptMessage] = []
    duration: int = 0  # Duration in seconds
    status: SessionStatus = SessionStatus.ACTIVE
    
    # Session metadata
    session_notes: Optional[str] = None
    
    # Audio recording
    audio_file_id: Optional[str] = None  # GridFS file ID for session recording
    
    # Audio settings used during session
    audio_enabled: bool = True
    voice_type: Optional[str] = None
    voice_speed: Optional[float] = None
    
    # Insights (generated after session completion)
    insights: Optional[SessionInsights] = None
    insights_generated: bool = False
    
    # Legacy fields for backward compatibility (all optional)
    score: Optional[int] = None  # Deprecated - use insights.overall_score
    feedback: Optional[str] = None  # Deprecated - use insights.session_summary
    ai_analysis: Optional[Dict[str, Any]] = None  # Deprecated - use insights
    analysis: Optional[str] = None  # Deprecated - use insights.session_summary
    performance_metrics: Optional[Dict[str, Any]] = None  # Deprecated - use insights
    
    # Additional AI analysis fields (optional for backward compatibility)
    conversation_flow_analysis: Optional[Dict[str, Any]] = None
    therapeutic_techniques_used: Optional[List[str]] = None
    patient_response_patterns: Optional[Dict[str, Any]] = None
    session_quality_metrics: Optional[Dict[str, Any]] = None
    improvement_suggestions: Optional[List[str]] = None
    clinical_observations: Optional[Dict[str, Any]] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class SessionCreate(BaseModel):
    patient_id: str
    audio_enabled: bool = True
    voice_type: Optional[str] = None
    voice_speed: Optional[float] = None
    
    class Config:
        populate_by_name = True


class SessionUpdate(BaseModel):
    end_time: Optional[datetime] = None
    transcript: Optional[List[TranscriptMessage]] = None
    duration: Optional[int] = None
    score: Optional[int] = None
    feedback: Optional[str] = None
    status: Optional[SessionStatus] = None
    session_notes: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    performance_metrics: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
    id: str = Field(alias="_id")
    student_id: str
    patient_id: str
    patient_name: Optional[str] = None  # Added for frontend display
    start_time: datetime
    end_time: Optional[datetime] = None
    transcript: List[TranscriptMessage] = []
    duration: int = 0
    status: SessionStatus
    session_notes: Optional[str] = None
    audio_enabled: bool
    voice_type: Optional[str] = None
    voice_speed: Optional[float] = None
    
    # Insights
    insights: Optional[SessionInsights] = None
    insights_generated: bool = False
    
    # Legacy fields for backward compatibility
    score: Optional[int] = None
    feedback: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    analysis: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    
    # Additional AI analysis fields (optional for backward compatibility)
    conversation_flow_analysis: Optional[Dict[str, Any]] = None
    therapeutic_techniques_used: Optional[List[str]] = None
    patient_response_patterns: Optional[Dict[str, Any]] = None
    session_quality_metrics: Optional[Dict[str, Any]] = None
    improvement_suggestions: Optional[List[str]] = None
    clinical_observations: Optional[Dict[str, Any]] = None
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class AddMessageRequest(BaseModel):
    speaker: MessageSpeaker
    text: str
    audio_url: Optional[str] = None


class SessionStats(BaseModel):
    total_sessions: int
    average_score: float
    hours_completed: float
    current_streak: int
    sessions_this_week: int
    sessions_this_month: int
    improvement_trend: float  # Percentage improvement over time


class SessionHistoryFilter(BaseModel):
    student_id: Optional[str] = None
    patient_id: Optional[str] = None
    status: Optional[SessionStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    limit: int = 50
    offset: int = 0
    sort_by: str = "start_time"  # start_time, score, duration
    sort_order: str = "desc"  # asc, desc