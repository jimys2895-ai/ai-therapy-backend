from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from bson import ObjectId
from datetime import datetime


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Patient(BaseModel):
    id: str = Field(alias="_id")
    name: str
    age: int
    condition: str
    personality: str
    background: str
    difficulty: DifficultyLevel
    avatar: str
    symptoms: List[str]
    emotional_state: str
    
    # Clinical details from patient info
    pronouns: Optional[str] = None
    occupation: Optional[str] = None
    presenting_problem: Optional[str] = None
    
    # Biopsychosocial profile
    biological_profile: Optional[str] = None
    psychological_profile: Optional[str] = None
    social_profile: Optional[str] = None
    somatic_profile: Optional[str] = None
    
    # History and background details
    detailed_history: Optional[str] = None
    strengths: Optional[List[str]] = None
    barriers: Optional[List[str]] = None
    learning_objectives: Optional[List[str]] = None
    
    # AI simulation responses
    dialogue_responses: Optional[List[str]] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class PatientCreate(BaseModel):
    name: str
    age: int
    condition: str
    personality: str
    background: str
    difficulty: DifficultyLevel
    avatar: str
    symptoms: List[str]
    emotional_state: str
    pronouns: Optional[str] = None
    occupation: Optional[str] = None
    presenting_problem: Optional[str] = None
    biological_profile: Optional[str] = None
    psychological_profile: Optional[str] = None
    social_profile: Optional[str] = None
    somatic_profile: Optional[str] = None
    detailed_history: Optional[str] = None
    strengths: Optional[List[str]] = None
    barriers: Optional[List[str]] = None
    learning_objectives: Optional[List[str]] = None
    dialogue_responses: Optional[List[str]] = None


class PatientResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    age: int
    condition: str
    personality: str
    background: str
    difficulty: DifficultyLevel
    avatar: str
    symptoms: List[str]
    emotional_state: str
    pronouns: Optional[str] = None
    occupation: Optional[str] = None
    presenting_problem: Optional[str] = None
    biological_profile: Optional[str] = None
    psychological_profile: Optional[str] = None
    social_profile: Optional[str] = None
    somatic_profile: Optional[str] = None
    detailed_history: Optional[str] = None
    strengths: Optional[List[str]] = None
    barriers: Optional[List[str]] = None
    learning_objectives: Optional[List[str]] = None
    dialogue_responses: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    is_active: bool
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    condition: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    difficulty: Optional[DifficultyLevel] = None
    avatar: Optional[str] = None
    symptoms: Optional[List[str]] = None
    emotional_state: Optional[str] = None
    pronouns: Optional[str] = None
    occupation: Optional[str] = None
    presenting_problem: Optional[str] = None
    biological_profile: Optional[str] = None
    psychological_profile: Optional[str] = None
    social_profile: Optional[str] = None
    somatic_profile: Optional[str] = None
    detailed_history: Optional[str] = None
    strengths: Optional[List[str]] = None
    barriers: Optional[List[str]] = None
    learning_objectives: Optional[List[str]] = None
    dialogue_responses: Optional[List[str]] = None
    is_active: Optional[bool] = None