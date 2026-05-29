from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field

from ....database import get_settings_collection
from ....models.settings import (
    UserSettings, UserSettingsCreate, UserSettingsResponse, UserSettingsUpdate,
    NotificationSettingsUpdate, AudioSettingsUpdate, DisplaySettingsUpdate, PrivacySettingsUpdate,
    NotificationSettings, AudioSettings, DisplaySettings, PrivacySettings
)
from ....auth.dependencies import get_current_user
from ....models.users import User

router = APIRouter()

# Response models for OpenAPI documentation
class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message", example="Operation completed successfully")


@router.get("/",
    response_model=UserSettingsResponse,
    summary="Get user settings",
    description="Retrieve user's application settings, creating defaults if they don't exist",
    responses={
        200: {
            "description": "User settings retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "user_id": "507f1f77bcf86cd799439012",
                        "notifications": {
                            "sessions": True,
                            "feedback": True,
                            "updates": False,
                            "email_notifications": True,
                            "push_notifications": False
                        },
                        "audio": {
                            "enabled": True,
                            "volume": 80,
                            "voice_type": "female",
                            "voice_speed": 1.0,
                            "speech_recognition_language": "en-US"
                        },
                        "display": {
                            "theme": "light",
                            "animations": True,
                            "font_size": "medium"
                        },
                        "privacy": {
                            "data_collection": True,
                            "analytics": True,
                            "session_recording": True
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve user settings"}
    }
)
async def get_user_settings(
    current_user: User = Depends(get_current_user)
):
    """
    Get user's application settings.
    
    Retrieves comprehensive user settings including:
    - **Notification preferences**: Session reminders, feedback notifications
    - **Audio settings**: Voice type, speed, volume, language preferences
    - **Display settings**: Theme, animations, font size, accessibility options
    - **Privacy settings**: Data collection, analytics, session recording preferences
    
    If no settings exist, creates default settings automatically.
    """
    try:
        settings_collection = get_settings_collection()
        
        # Try to find existing settings
        settings = await settings_collection.find_one({"user_id": current_user.id})
        
        if not settings:
            # Create default settings
            default_settings = {
                "_id": str(ObjectId()),
                "user_id": current_user.id,
                "notifications": NotificationSettings().dict(),
                "audio": AudioSettings().dict(),
                "display": DisplaySettings().dict(),
                "privacy": PrivacySettings().dict(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            await settings_collection.insert_one(default_settings)
            settings = default_settings
        
        return UserSettingsResponse(**settings)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user settings: {str(e)}"
        )


@router.put("/",
    response_model=UserSettingsResponse,
    summary="Update user settings",
    description="Update comprehensive user application settings",
    responses={
        200: {
            "description": "User settings updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "user_id": "507f1f77bcf86cd799439012",
                        "notifications": {
                            "sessions": False,
                            "feedback": True,
                            "updates": True
                        },
                        "audio": {
                            "enabled": True,
                            "volume": 90,
                            "voice_type": "male"
                        },
                        "updated_at": "2024-01-21T15:30:00Z"
                    }
                }
            }
        },
        404: {"description": "User settings not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to update user settings"}
    }
)
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update comprehensive user application settings.
    
    Allows updating multiple setting categories at once:
    - **notifications**: Session reminders, feedback notifications, platform updates
    - **audio**: Voice preferences, volume, speed, language settings
    - **display**: Theme, animations, font size, accessibility options
    - **privacy**: Data collection, analytics, session recording preferences
    
    Only provided fields will be updated, existing settings remain unchanged.
    """
    try:
        print(f"Updating settings for user: {current_user.id}")
        print(f"Settings update data: {settings_update}")
        
        settings_collection = get_settings_collection()
        
        # Check if settings exist
        existing_settings = await settings_collection.find_one({"user_id": current_user.id})
        if not existing_settings:
            print(f"No existing settings found for user: {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User settings not found. Please get settings first to create defaults."
            )
        
        print(f"Existing settings: {existing_settings}")
        
        # Prepare update data
        update_data = {}
        
        if settings_update.notifications:
            # Merge with existing notifications to handle partial updates
            current_notifications = existing_settings.get("notifications", {})
            notification_updates = {k: v for k, v in settings_update.notifications.dict(exclude_unset=True).items() if v is not None}
            current_notifications.update(notification_updates)
            update_data["notifications"] = current_notifications
        
        if settings_update.audio:
            # Merge with existing audio settings to handle partial updates
            current_audio = existing_settings.get("audio", {})
            audio_updates = {k: v for k, v in settings_update.audio.dict(exclude_unset=True).items() if v is not None}
            current_audio.update(audio_updates)
            update_data["audio"] = current_audio
        
        if settings_update.display:
            # Merge with existing display settings to handle partial updates
            current_display = existing_settings.get("display", {})
            display_updates = {k: v for k, v in settings_update.display.dict(exclude_unset=True).items() if v is not None}
            current_display.update(display_updates)
            update_data["display"] = current_display
        
        if settings_update.privacy:
            # Merge with existing privacy settings to handle partial updates
            current_privacy = existing_settings.get("privacy", {})
            privacy_updates = {k: v for k, v in settings_update.privacy.dict(exclude_unset=True).items() if v is not None}
            current_privacy.update(privacy_updates)
            update_data["privacy"] = current_privacy
        
        update_data["updated_at"] = datetime.utcnow()
        
        print(f"Final update data: {update_data}")
        
        # Update settings
        result = await settings_collection.update_one(
            {"user_id": current_user.id},
            {"$set": update_data}
        )
        
        print(f"Update result: matched={result.matched_count}, modified={result.modified_count}")
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User settings not found for update"
            )
        
        # Get updated settings
        updated_settings = await settings_collection.find_one({"user_id": current_user.id})
        if not updated_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Settings not found after update"
            )
        return UserSettingsResponse(**updated_settings)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user settings: {str(e)}"
        )


@router.put("/notifications",
    response_model=UserSettingsResponse,
    summary="Update notification settings",
    description="Update only notification preferences without affecting other settings",
    responses={
        200: {
            "description": "Notification settings updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "user_id": "507f1f77bcf86cd799439012",
                        "notifications": {
                            "sessions": False,
                            "feedback": True,
                            "updates": True,
                            "email_notifications": False,
                            "push_notifications": True
                        },
                        "updated_at": "2024-01-21T15:30:00Z"
                    }
                }
            }
        },
        404: {"description": "User settings not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to update notification settings"}
    }
)
async def update_notification_settings(
    notification_update: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update only notification preferences.
    
    Allows granular control over notification settings:
    - **sessions**: Session reminder notifications
    - **feedback**: AI feedback and scoring notifications
    - **updates**: Platform updates and new feature announcements
    - **email_notifications**: Enable/disable email notifications
    - **push_notifications**: Enable/disable push notifications
    
    Only provided fields will be updated, other notification settings remain unchanged.
    """
    try:
        settings_collection = get_settings_collection()
        
        # Get existing settings
        existing_settings = await settings_collection.find_one({"user_id": current_user.id})
        if not existing_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User settings not found"
            )
        
        # Update only the notification fields that are provided
        current_notifications = existing_settings.get("notifications", {})
        update_data = {k: v for k, v in notification_update.dict().items() if v is not None}
        
        # Merge with existing notifications
        current_notifications.update(update_data)
        
        # Update in database
        await settings_collection.update_one(
            {"user_id": current_user.id},
            {
                "$set": {
                    "notifications": current_notifications,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Get updated settings
        updated_settings = await settings_collection.find_one({"user_id": current_user.id})
        return UserSettingsResponse(**updated_settings)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update notification settings: {str(e)}"
        )


@router.put("/audio",
    response_model=UserSettingsResponse,
    summary="Update audio settings",
    description="Update only audio preferences without affecting other settings",
    responses={
        200: {
            "description": "Audio settings updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "user_id": "507f1f77bcf86cd799439012",
                        "audio": {
                            "enabled": True,
                            "volume": 90,
                            "voice_type": "male",
                            "voice_speed": 1.2,
                            "speech_recognition_language": "en-GB",
                            "auto_play_responses": False
                        },
                        "updated_at": "2024-01-21T15:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid volume or voice speed range"},
        404: {"description": "User settings not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to update audio settings"}
    }
)
async def update_audio_settings(
    audio_update: AudioSettingsUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update only audio preferences.
    
    Allows granular control over audio settings:
    - **enabled**: Enable/disable all audio features
    - **volume**: Audio volume level (0-100)
    - **voice_type**: AI voice type (female, male, neutral)
    - **voice_speed**: Speech speed multiplier (0.5-2.0)
    - **speech_recognition_language**: Language for speech recognition
    - **auto_play_responses**: Automatically play AI responses
    
    Volume must be between 0-100, voice speed between 0.5-2.0.
    Only provided fields will be updated, other audio settings remain unchanged.
    """
    try:
        settings_collection = get_settings_collection()
        
        # Get existing settings
        existing_settings = await settings_collection.find_one({"user_id": current_user.id})
        if not existing_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User settings not found"
            )
        
        # Update only the audio fields that are provided
        current_audio = existing_settings.get("audio", {})
        update_data = {k: v for k, v in audio_update.dict().items() if v is not None}
        
        # Validate volume range
        if "volume" in update_data and not (0 <= update_data["volume"] <= 100):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Volume must be between 0 and 100"
            )
        
        # Validate voice speed range
        if "voice_speed" in update_data and not (0.5 <= update_data["voice_speed"] <= 2.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Voice speed must be between 0.5 and 2.0"
            )
        
        # Merge with existing audio settings
        current_audio.update(update_data)
        
        # Update in database
        await settings_collection.update_one(
            {"user_id": current_user.id},
            {
                "$set": {
                    "audio": current_audio,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Get updated settings
        updated_settings = await settings_collection.find_one({"user_id": current_user.id})
        return UserSettingsResponse(**updated_settings)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update audio settings: {str(e)}"
        )


@router.put("/display",
    response_model=UserSettingsResponse,
    summary="Update display settings",
    description="Update only display preferences without affecting other settings",
    responses={
        200: {
            "description": "Display settings updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "user_id": "507f1f77bcf86cd799439012",
                        "display": {
                            "theme": "dark",
                            "animations": False,
                            "font_size": "large",
                            "high_contrast": True,
                            "reduce_motion": True
                        },
                        "updated_at": "2024-01-21T15:30:00Z"
                    }
                }
            }
        },
        404: {"description": "User settings not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to update display settings"}
    }
)
async def update_display_settings(
    display_update: DisplaySettingsUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update only display preferences.
    
    Allows granular control over display settings:
    - **theme**: Visual theme (light, dark, auto)
    - **animations**: Enable/disable UI animations
    - **font_size**: Text size (small, medium, large)
    - **high_contrast**: Enable high contrast mode for accessibility
    - **reduce_motion**: Reduce motion for users with vestibular disorders
    
    Only provided fields will be updated, other display settings remain unchanged.
    """
    try:
        settings_collection = get_settings_collection()
        
        # Get existing settings
        existing_settings = await settings_collection.find_one({"user_id": current_user.id})
        if not existing_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User settings not found"
            )
        
        # Update only the display fields that are provided
        current_display = existing_settings.get("display", {})
        update_data = {k: v for k, v in display_update.dict().items() if v is not None}
        
        # Merge with existing display settings
        current_display.update(update_data)
        
        # Update in database
        await settings_collection.update_one(
            {"user_id": current_user.id},
            {
                "$set": {
                    "display": current_display,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Get updated settings
        updated_settings = await settings_collection.find_one({"user_id": current_user.id})
        return UserSettingsResponse(**updated_settings)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update display settings: {str(e)}"
        )


@router.put("/privacy", response_model=UserSettingsResponse)
async def update_privacy_settings(
    privacy_update: PrivacySettingsUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update only privacy settings"""
    try:
        settings_collection = get_settings_collection()
        
        # Get existing settings
        existing_settings = await settings_collection.find_one({"user_id": current_user.id})
        if not existing_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User settings not found"
            )
        
        # Update only the privacy fields that are provided
        current_privacy = existing_settings.get("privacy", {})
        update_data = {k: v for k, v in privacy_update.dict().items() if v is not None}
        
        # Merge with existing privacy settings
        current_privacy.update(update_data)
        
        # Update in database
        await settings_collection.update_one(
            {"user_id": current_user.id},
            {
                "$set": {
                    "privacy": current_privacy,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Get updated settings
        updated_settings = await settings_collection.find_one({"user_id": current_user.id})
        return UserSettingsResponse(**updated_settings)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update privacy settings: {str(e)}"
        )


@router.delete("/")
async def reset_user_settings(
    current_user: User = Depends(get_current_user)
):
    """Reset user settings to defaults"""
    try:
        settings_collection = get_settings_collection()
        
        # Create default settings
        default_settings = {
            "user_id": current_user.id,
            "notifications": NotificationSettings().dict(),
            "audio": AudioSettings().dict(),
            "display": DisplaySettings().dict(),
            "privacy": PrivacySettings().dict(),
            "updated_at": datetime.utcnow()
        }
        
        # Update or create settings
        await settings_collection.update_one(
            {"user_id": current_user.id},
            {"$set": default_settings},
            upsert=True
        )
        
        return {"message": "User settings reset to defaults successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset user settings: {str(e)}"
        )