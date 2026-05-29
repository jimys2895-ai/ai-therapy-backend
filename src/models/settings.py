from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
from bson import ObjectId
from datetime import datetime


class VoiceType(str, Enum):
    FEMALE = "female"
    MALE = "male"
    NEUTRAL = "neutral"


class ThemeType(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class FontSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class NotificationSettings(BaseModel):
    sessions: bool = True
    feedback: bool = True
    updates: bool = False
    email_notifications: bool = True


class AudioSettings(BaseModel):
    enabled: bool = True
    volume: int = 80  # 0-100
    voice_type: VoiceType = VoiceType.FEMALE
    voice_speed: float = 1.0  # 0.5-2.0
    speech_recognition_language: str = "en-US"
    auto_play_responses: bool = True


class DisplaySettings(BaseModel):
    theme: ThemeType = ThemeType.LIGHT
    animations: bool = True
    font_size: FontSize = FontSize.MEDIUM
    high_contrast: bool = False
    reduce_motion: bool = False


class PrivacySettings(BaseModel):
    data_collection: bool = True
    analytics: bool = True
    session_recording: bool = True


class UserSettings(BaseModel):
    id: str = Field(alias="_id")
    user_id: str  # Reference to User
    
    # Settings categories
    notifications: NotificationSettings = NotificationSettings()
    audio: AudioSettings = AudioSettings()
    display: DisplaySettings = DisplaySettings()
    privacy: PrivacySettings = PrivacySettings()
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# Individual setting update models for granular updates
class NotificationSettingsUpdate(BaseModel):
    sessions: Optional[bool] = None
    feedback: Optional[bool] = None
    updates: Optional[bool] = None
    email_notifications: Optional[bool] = None


class AudioSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    volume: Optional[int] = None
    voice_type: Optional[VoiceType] = None
    voice_speed: Optional[float] = None
    speech_recognition_language: Optional[str] = None
    auto_play_responses: Optional[bool] = None


class DisplaySettingsUpdate(BaseModel):
    theme: Optional[ThemeType] = None
    animations: Optional[bool] = None
    font_size: Optional[FontSize] = None
    high_contrast: Optional[bool] = None
    reduce_motion: Optional[bool] = None


class PrivacySettingsUpdate(BaseModel):
    data_collection: Optional[bool] = None
    analytics: Optional[bool] = None
    session_recording: Optional[bool] = None


class UserSettingsCreate(BaseModel):
    user_id: str
    notifications: Optional[NotificationSettings] = None
    audio: Optional[AudioSettings] = None
    display: Optional[DisplaySettings] = None
    privacy: Optional[PrivacySettings] = None


class UserSettingsUpdate(BaseModel):
    notifications: Optional[NotificationSettingsUpdate] = None
    audio: Optional[AudioSettingsUpdate] = None
    display: Optional[DisplaySettingsUpdate] = None
    privacy: Optional[PrivacySettingsUpdate] = None


class UserSettingsResponse(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    notifications: NotificationSettings
    audio: AudioSettings
    display: DisplaySettings
    privacy: PrivacySettings
    created_at: datetime
    updated_at: datetime
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}