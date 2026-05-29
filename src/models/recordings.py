"""
Recording models for voice therapy sessions
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

class Recording(BaseModel):
    """Recording model for storing session audio, transcripts, and analysis"""
    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId")
    session_id: str = Field(..., description="ID of the therapy session")
    patient_id: str = Field(..., description="ID of the patient")
    student_id: str = Field(..., description="ID of the student therapist")
    patient_name: str = Field(..., description="Name of the patient")
    
    # Audio and transcript data
    audio_url: Optional[str] = Field(None, description="URL or GridFS ID of the audio file")
    transcription: str = Field(..., description="Full session transcript")
    analysis: str = Field(..., description="Session analysis and insights")
    
    # Session metadata
    session_duration: int = Field(0, description="Session duration in seconds")
    message_count: int = Field(0, description="Total number of messages in session")
    session_score: int = Field(0, description="Session performance score")
    session_feedback: str = Field("", description="Session feedback")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "session_id": "507f1f77bcf86cd799439011",
                "patient_id": "507f1f77bcf86cd799439012",
                "student_id": "507f1f77bcf86cd799439013",
                "patient_name": "Natalie Rosen",
                "audio_url": "gridfs://507f1f77bcf86cd799439014",
                "transcription": "[10:30:15] Student: Hello, how are you feeling today?\n[10:30:18] Patient: Not great, I guess.",
                "analysis": "Session analysis with insights and recommendations",
                "session_duration": 1800,
                "message_count": 24,
                "session_score": 85,
                "session_feedback": "Good session with effective communication"
            }
        }

class RecordingResponse(BaseModel):
    """Response model for recording data"""
    recordings: List[Recording]
    total: int
    limit: int
    skip: int

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class RecordingCreate(BaseModel):
    """Model for creating a new recording"""
    session_id: str
    patient_id: str
    student_id: str
    patient_name: str
    transcription: str
    analysis: Optional[str] = None
    audio_url: Optional[str] = None
    session_duration: int = 0
    message_count: int = 0
    session_score: int = 0
    session_feedback: str = ""

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}