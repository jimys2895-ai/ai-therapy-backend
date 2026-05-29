from passlib.context import CryptContext
from datetime import datetime, timedelta
from ..database import get_users_collection
from ..models.users import User
from ..config import settings
from bson import ObjectId
import pytz




pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

async def get_user_by_email(email: str) -> User:
    """Get user by email from database"""
    users_collection = get_users_collection()
    user_data = await users_collection.find_one({"email": email})
    if user_data:
        # Convert ObjectId to string for Pydantic model
        user_data["_id"] = str(user_data["_id"])
        return User(**user_data)
    return None

async def get_user_by_username(username: str) -> User:
    """Get user by username from database"""
    users_collection = get_users_collection()
    user_data = await users_collection.find_one({"username": username})
    if user_data:
        # Convert ObjectId to string for Pydantic model
        user_data["_id"] = str(user_data["_id"])
        return User(**user_data)
    return None

async def get_user_by_id(user_id: str) -> User:
    """Get user by ID from database"""
    users_collection = get_users_collection()
    user_data = await users_collection.find_one({"_id": ObjectId(user_id)})
    if user_data:
        # Convert ObjectId to string for Pydantic model
        user_data["_id"] = str(user_data["_id"])
        return User(**user_data)
    return None

async def authenticate_user(email: str, password: str) -> User:
    """Authenticate user with email and password"""
    user = await get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user

async def authenticate_user_by_username_or_email(username_or_email: str, password: str) -> User:
    """Authenticate user with username or email and password"""
    # Try to find user by username first
    user = await get_user_by_username(username_or_email)
    
    # If not found by username, try by email
    if not user:
        user = await get_user_by_email(username_or_email)
    
    # If still not found, return None
    if not user:
        return None
    
    # Verify password
    if not verify_password(password, user.hashed_password):
        return None
    
    # Check if user is active
    if not user.is_active:
        return None
    
    return user

async def update_user_login(user_id: str):
    """Update user's last login time"""
    users_collection = get_users_collection()
    tz = pytz.timezone(settings.TIMEZONE)
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"last_login": datetime.now(tz)}}
    )

async def reset_daily_credits(user: User) -> int:
    """Reset daily credits if needed and return current credits"""
    # In your current model, there are no credits/credits_reset_date fields
    # Instead, we'll use the message_count/max_messages fields
    
    # Return remaining message count
    if hasattr(user, 'max_messages') and user.max_messages == -1:
        # Unlimited messages
        return float('inf')
    
    # For message-based systems, just return remaining messages
    if hasattr(user, 'message_count') and hasattr(user, 'max_messages'):
        remaining = user.max_messages - user.message_count
        return max(0, remaining)
    
    # Default fallback - no limit tracking
    return 0

async def use_credit(user_id: str) -> bool:
    """Use one message and return True if successful"""
    users_collection = get_users_collection()
    user = await get_user_by_id(user_id)
    
    if not user:
        return False
    
    from ..models.users import PlanType
    if user.subscription_plan != PlanType.FREE or user.max_messages == -1:
        return True
    
    # Check if user has messages left
    if user.message_count < user.max_messages:
        # Increment message count
        result = await users_collection.update_one(
            {
                "_id": ObjectId(user_id),
                "message_count": {"$lt": user.max_messages}  # Only update if message_count < max_messages
            },
            {"$inc": {"message_count": 1}}
        )
        
        # Return True only if the update actually happened (matched_count > 0)
        return result.matched_count > 0
    
    return False

