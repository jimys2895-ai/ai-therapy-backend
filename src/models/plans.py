from pydantic import BaseModel, Field
from typing import Optional
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

class SubscriptionPlan(BaseModel):
    id: str = Field(alias="_id")
    name: PlanType
    stripe_price_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserSubscriptionResponse(BaseModel):
    plan_type: PlanType
    status: SubscriptionStatus
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    stripe_subscription_id: Optional[str] = None
    message_count: int = 0
    max_messages: int = 3
    trial_end: Optional[datetime] = None

class CancelSubscriptionRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional reason for cancellation")

class CancelSubscriptionResponse(BaseModel):
    message: str = Field(..., description="Cancellation status message")
    cancel_at_period_end: bool = Field(..., description="Whether subscription cancels at period end")
    current_period_end: Optional[datetime] = Field(None, description="When the subscription will actually end")
    plan_id: str
    status: SubscriptionStatus  # Use enum instead of string
    started_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
