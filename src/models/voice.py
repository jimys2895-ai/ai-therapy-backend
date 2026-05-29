from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from bson import ObjectId
from datetime import datetime


class VoiceConnectionStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class VoiceSessionSettings(BaseModel):
    """Voice settings for a therapy session"""
    voice_type: str = "alloy"  # OpenAI voice types: alloy, echo, fable, onyx, nova, shimmer
    voice_speed: float = 1.0
    language: str = "en-US"
    noise_reduction: bool = True
    auto_gain_control: bool = True
    echo_cancellation: bool = True
    audio_format: str = "pcm16"  # For OpenAI Realtime API
    sample_rate: int = 24000  # For OpenAI Realtime API


class VoiceSessionInfo(BaseModel):
    """Information about an active voice session"""
    session_id: str
    patient_id: str
    patient_name: str
    connection_status: VoiceConnectionStatus
    start_time: datetime
    settings: VoiceSessionSettings
    message_count: int = 0
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class RealtimeMessage(BaseModel):
    """Message structure for OpenAI Realtime API communication"""
    type: str
    audio: Optional[str] = None  # Base64 encoded audio
    text: Optional[str] = None
    speaker: Optional[str] = None  # "student" or "patient"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VoiceAnalytics(BaseModel):
    """Analytics for voice session performance"""
    session_id: str
    total_messages: int
    student_messages: int
    patient_messages: int
    session_duration: float  # in seconds
    average_response_time: float  # in seconds
    audio_quality_score: Optional[float] = None
    engagement_score: Optional[float] = None
    therapeutic_progress_indicators: Optional[Dict[str, Any]] = None
    
    class Config:
        populate_by_name = True


class VoiceError(BaseModel):
    """Voice system error information"""
    error_type: str
    message: str
    session_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None


# Legacy models for backward compatibility (simplified)
class VoiceSettings(BaseModel):
    voice_type: str = "alloy"
    voice_speed: float = 1.0
    language: str = "en-US"
    noise_reduction: bool = True
    auto_gain_control: bool = True
    echo_cancellation: bool = True