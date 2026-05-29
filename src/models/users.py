from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from enum import Enum
from bson import ObjectId
from datetime import datetime


class PlanType(str, Enum):
    FREE = "free"
    MONTHLY = "monthly"
    LIFETIME = "lifetime"
    PROFESSIONAL = "professional"

class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    EXPIRED = "expired"

class UserType(str, Enum):
    CUSTOMER = "customer"
    MODERATOR = "moderator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

class AccountStatus(str, Enum):
    REQUESTED = "requested"      # New registration, pending approval
    ACTIVATED = "activated"      # Approved and active
    DEACTIVATED = "deactivated"  # Temporarily disabled
    REJECTED = "rejected"        # Permanently rejected
    REFUSED = "refused"          # Access refused

class User(BaseModel):
    id: str = Field(alias="_id")
    uuid: Optional[str] = None  # Added UUID field
    email: EmailStr
    hashed_password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None  # For frontend compatibility
    createdAt: Optional[datetime] = None  # For frontend compatibility
    subscription: Optional[str] = None  # For frontend compatibility ('free' | 'monthly' | 'lifetime')
    provider: Optional[str] = None
    picture: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    
    # Subscription fields
    subscription_plan: PlanType = PlanType.FREE
    subscription_status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    trial_start_date: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    subscription_expiry: Optional[datetime] = None
    
    display_name: Optional[str] = None
    
    # Message tracking - core feature for free users
    message_count: int = 0  # Track number of messages sent
    max_messages: int = 3  # Max allowed messages (default 3 for free, -1 for unlimited/paid)
    
    # Legacy trial tracking (kept for compatibility)
    used_trial: bool = False  # Track if user has used their trial
    trial_active: bool = False  # Track if trial is currently active
    trial_days: int = 0  # Days remaining in trial
    
    # Stripe integration
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_cancel_at_period_end: Optional[bool] = False
    subscription_current_period_end: Optional[datetime] = None
    
    # Admin fields
    user_type: UserType = UserType.CUSTOMER
    account_status: AccountStatus = AccountStatus.REQUESTED
    status_changed_at: Optional[datetime] = None
    status_changed_by: Optional[str] = None  # Admin user ID who changed the status
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    refresh_token: Optional[str] = None
    refresh_token_expires_at: Optional[datetime] = None
    
    # Password reset workflow (admin-mediated reset requests)
    reset_request: bool = False  # When true, user has requested an admin password reset
    reset_requested_at: Optional[datetime] = None  # Timestamp of latest reset request
    
    # Therapy platform specific fields
    university: Optional[str] = None  # For student users
    year: Optional[int] = None  # Academic year for students
    role: Optional[str] = None  # Frontend compatibility field ('student' | 'admin')
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str  # Can be email or username
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class LoginRequest(BaseModel):
    username: str  # Email is used as username
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: 'UserResponse'

class UpdateUserDto(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    university: Optional[str] = None
    year: Optional[int] = None

class UserResponse(BaseModel):
    id: str = Field(alias="_id")
    uuid: Optional[str] = None  # Added UUID field
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None  # For frontend compatibility
    createdAt: Optional[datetime] = None  # For frontend compatibility
    subscription: Optional[str] = None  # For frontend compatibility ('free' | 'monthly' | 'lifetime')
    provider: Optional[str] = None
    picture: Optional[str] = None
    is_active: bool
    is_superuser: bool = False
    
    # Frontend-specific fields
    display_name: Optional[str] = None
    subscription_plan: PlanType
    subscription_status: SubscriptionStatus
    trial_start_date: Optional[datetime] = None
    subscription_expiry: Optional[datetime] = None
    
    # Message tracking - core feature for free users
    message_count: int = 0  # Track number of messages sent
    max_messages: int = 3  # Max allowed messages (default 3 for free, -1 for unlimited/paid)
    
    # Legacy trial tracking (kept for compatibility)
    used_trial: bool = False  # Track if user has used their trial
    trial_active: bool = False  # Track if trial is currently active
    trial_days: int = 0  # Days remaining in trial
    
    # Admin fields
    user_type: UserType
    account_status: AccountStatus
    status_changed_at: Optional[datetime] = None
    status_changed_by: Optional[str] = None  # Admin user ID who changed the status
    created_at: datetime
    last_login: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_cancel_at_period_end: Optional[bool] = False
    subscription_current_period_end: Optional[datetime] = None
    
    # Password reset workflow
    reset_request: bool = False
    reset_requested_at: Optional[datetime] = None
    
    # Therapy platform specific fields
    university: Optional[str] = None  # For student users
    year: Optional[int] = None  # Academic year for students
    role: Optional[str] = None  # Frontend compatibility field ('student' | 'admin')
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

