from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Union
from datetime import datetime

from ....models.plans import UserSubscriptionResponse, PlanType, SubscriptionStatus
from ....models.users import User
from ....auth.dependencies import get_current_active_user

router = APIRouter()

class PlanInfo(BaseModel):
    name: str
    display_name: str
    price: float
    currency: str
    billing_period: str
    features: List[str]

@router.get("/plans",
    response_model=List[PlanInfo],
    summary="Get available plans",
    description="Get list of available subscription plans"
)
async def get_plans():
    """
    Get available subscription plans.
    
    Returns basic plan information. Detailed features and pricing
    are handled on the frontend.
    """
    plans = [
        PlanInfo(
            name="monthly",
            display_name="Monthly",
            price=19.99,
            currency="usd",
            billing_period="month",
            features=[
                "Unlimited AI coaching sessions",
                "24/7 access",
                "Goal tracking"
            ]
        ),
        PlanInfo(
            name="lifetime",
            display_name="Lifetime (Students Only)",
            price=197.0,
            currency="usd",
            billing_period="lifetime",
            features=[
                "Everything in Monthly",
                "Lifetime access",
                "Priority support",
                "Future updates included",
                "Students only - must use valid .edu email"
            ]
        ),
        PlanInfo(
            name="professional",
            display_name="Professional",
            price=697.0,
            currency="usd",
            billing_period="lifetime",
            features=[
                "Everything in Monthly",
                "Lifetime access",
                "Priority support",
                "Future updates included",
                "Advanced features",
                "Premium support"
            ]
        )
    ]
    return plans



@router.get("/current",
    response_model=UserSubscriptionResponse,
    summary="Get current subscription",
    description="Get current user's subscription details and message status",
    responses={
        200: {
            "description": "Subscription details retrieved successfully"
        },
        401: {"description": "Authentication required"}
    }
)
async def get_current_subscription(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's subscription details.
    
    Returns subscription information with message counts and limits.
    Teen users always have unlimited access.
    Adult users have trial/subscription limits.
    """
    return UserSubscriptionResponse(
        plan_type=current_user.subscription_plan,
        status=current_user.subscription_status,
        current_period_end=current_user.subscription_expiry,
        cancel_at_period_end=current_user.subscription_cancel_at_period_end or False,
        stripe_subscription_id=current_user.stripe_subscription_id,
    )
