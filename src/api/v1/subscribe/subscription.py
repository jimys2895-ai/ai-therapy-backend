from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
import stripe
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from ....models.users import User, PlanType, SubscriptionStatus
from ....models.plans import UserSubscriptionResponse, CancelSubscriptionRequest, CancelSubscriptionResponse
from ....database import get_users_collection, get_subscriptions_collection
from ....auth.dependencies import get_current_active_user
from ....config import settings
from bson import ObjectId

router = APIRouter()

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Plan configurations with Stripe price IDs
PLAN_CONFIGS = {
    "monthly": {
        "stripe_price_id": "price_1Rp4p1GgO57iQwYIagjdIrml",  # Monthly plan price ID from stripe
        "name": "Monthly",
        "price": 19.99,
        "currency": "usd"
    },
    "lifetime": {
        "stripe_price_id": "price_1Rp4paGgO57iQwYI66aUwO1K",  # Lifetime plan price ID from stripe
        "name": "Lifetime (Students Only)",
        "price": 197.00,
        "currency": "usd"
    },
    "professional": {
        "stripe_price_id": "price_1RseeKGgO57iQwYIXm4qyrVh",  # Professional plan price ID from stripe
        "name": "Professional",
        "price": 697.00,
        "currency": "usd"
    }
}

class CreateCheckoutSessionRequest(BaseModel):
    plan_type: PlanType = Field(..., description="Plan to subscribe to")
    success_url: str = Field(..., description="URL to redirect after successful payment")
    cancel_url: str = Field(..., description="URL to redirect after cancelled payment")

class CheckoutSessionResponse(BaseModel):
    checkout_url: str = Field(..., description="Stripe checkout session URL")
    session_id: str = Field(..., description="Stripe session ID")

class StartTrialRequest(BaseModel):
    plan_type: PlanType = Field(..., description="Plan to start trial for")

class StartTrialResponse(BaseModel):
    message: str = Field(..., description="Success message")
    trial_end: datetime = Field(..., description="Trial end date")
    subscription_id: str = Field(..., description="Stripe subscription ID")

@router.post("/create-checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe checkout session",
    description="Create a Stripe checkout session for plan subscription"
)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create Stripe checkout session for plan subscription.
    """
    import logging
    logger = logging.getLogger("aitherapy.subscription")
    logger.info(f"[CHECKOUT] User: {getattr(current_user, 'id', None)} | Email: {getattr(current_user, 'email', None)} | Plan: {getattr(request, 'plan_type', None)} | Success URL: {getattr(request, 'success_url', None)} | Cancel URL: {getattr(request, 'cancel_url', None)}")
    logger.debug(f"[CHECKOUT] Request body: {request.dict()}")
    # Get plan configuration
    if request.plan_type not in PLAN_CONFIGS:
        logger.error(f"[CHECKOUT] Plan not found: {request.plan_type}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    plan_config = PLAN_CONFIGS[request.plan_type]
    logger.info(f"[CHECKOUT] Using plan config: {plan_config}")
    
    # Check if lifetime plan requires .edu email
    if request.plan_type.value == 'lifetime':
        def is_valid_edu_email(email: str) -> bool:
            """
            Validate that email is from a legitimate .edu domain.
            Checks for proper .edu format and prevents spoofing attempts.
            """
            email_lower = email.lower().strip()
            
            # Must end with .edu
            if not email_lower.endswith('.edu'):
                return False
            
            # Split email to get domain part
            try:
                local_part, domain = email_lower.rsplit('@', 1)
            except ValueError:
                return False
            
            # Domain must end with .edu (not just contain it)
            if not domain.endswith('.edu'):
                return False
            
            # Domain should be exactly .edu or subdomain.edu (not .eduanything)
            if domain == '.edu':  # Invalid: just .edu
                return False
            
            # Check for common spoofing patterns
            if '.edu.' in domain:  # Invalid: something.edu.something
                return False
            
            # Domain should have at least one character before .edu
            domain_without_edu = domain[:-4]  # Remove .edu
            if not domain_without_edu or '.' in domain_without_edu.split('.')[-1] == '':
                return False
            
            return True
        
        if not is_valid_edu_email(current_user.email):
            logger.error(f"[CHECKOUT] Invalid .edu email format. User email: {current_user.email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Lifetime plan is only available for students with valid .edu email addresses from accredited institutions"
            )
        logger.info(f"[CHECKOUT] .edu email validation passed for user: {current_user.email}")
    
    try:
        # Create or get Stripe customer
        is_new_customer = False
        if current_user.stripe_customer_id:
            customer_id = current_user.stripe_customer_id
            logger.info(f"[CHECKOUT] Existing Stripe customer: {customer_id}")
        else:
            customer = stripe.Customer.create(
                metadata={"user_id": str(current_user.id)},
                email=current_user.email
            )
            customer_id = customer.id
            is_new_customer = True
            logger.info(f"[CHECKOUT] Created new Stripe customer: {customer_id}")
            # Store customer ID in user document
            users_collection = get_users_collection()
            await users_collection.update_one(
                {"_id": ObjectId(current_user.id)},
                {"$set": {"stripe_customer_id": customer_id}}
            )
        # COMMENTED OUT - Trial functionality disabled for now
        # Check if user is eligible for a free trial
        # is_trial_eligible = (not getattr(current_user, 'used_trial', False)) and (not getattr(current_user, 'trial_active', False))
        # logger.info(f"[CHECKOUT] Trial eligible: {is_trial_eligible}")
        
        # Set trial eligibility to False to disable trials
        is_trial_eligible = False
        logger.info(f"[CHECKOUT] Trial disabled - is_trial_eligible set to False")
        
        # Prepare checkout session parameters
        checkout_params = {
            'customer': customer_id,
            'payment_method_types': ['card'],
            'line_items': [{
                'price': plan_config["stripe_price_id"],
                'quantity': 1,
            }],
            'mode': 'payment' if request.plan_type.value in ['lifetime', 'professional'] else 'subscription',
            'success_url': request.success_url,
            'cancel_url': request.cancel_url,
            'metadata': {
                'user_id': str(current_user.id),
                'plan_type': request.plan_type.value,
                'is_trial': str(is_trial_eligible)  # Will always be False now
            }
        }
        logger.debug(f"[CHECKOUT] Stripe checkout params: {checkout_params}")
        
        # COMMENTED OUT - Trial period functionality disabled
        # Only add trial for subscription mode (monthly), not for one-time payments (lifetime/professional)
        # if is_trial_eligible and request.plan_type.value not in ['lifetime', 'professional']:
        #     checkout_params['subscription_data'] = {
        #         'trial_period_days': 30,
        #         'trial_settings': {
        #             'end_behavior': {
        #                 'missing_payment_method': 'cancel'
        #             }
        #         },
        #         'metadata': {
        #             'user_id': str(current_user.id),
        #             'plan_type': request.plan_type.value,
        #             'trial_start': str(datetime.utcnow().isoformat())
        #         }
        #     }
        #     logger.info(f"[CHECKOUT] Added trial period to subscription_data.")
        
        logger.info(f"[CHECKOUT] Trial functionality disabled - proceeding with direct subscription")
        # Create Stripe checkout session
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        logger.info(f"[CHECKOUT] Created Stripe checkout session: {checkout_session.id} | URL: {checkout_session.url}")
        return {
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }
    except stripe.error.StripeError as e:
        logger.error(f"[CHECKOUT] Stripe error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stripe error: {str(e)}"
        )

# COMMENTED OUT - Using message-based system instead of Stripe trials
# @router.post("/start-trial",
#     response_model=StartTrialResponse,
#     summary="Start free trial",
#     description="Start a free trial without payment method collection"
# )
# async def start_trial(
#     request: StartTrialRequest,
#     current_user: User = Depends(get_current_active_user)
# ):
#     """
#     Start a free trial without collecting payment method.
#     Only available for users who haven't had a trial before.
#     """
#     # COMMENTED OUT - Using message-based system instead of Stripe trials

@router.get("/current",
    response_model=UserSubscriptionResponse,
    summary="Get current user subscription",
    description="Get the current user's subscription details"
)
async def get_current_subscription(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's subscription details.
    """
    if not current_user.stripe_subscription_id:
        return UserSubscriptionResponse(
            plan_type=current_user.subscription_plan,
            status=current_user.subscription_status,
            current_period_end=current_user.subscription_expiry,
            cancel_at_period_end=False,
            stripe_subscription_id=None,
            message_count=current_user.message_count,
            max_messages=current_user.max_messages
        )
    
    try:
        subscription = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
        
        current_period_end = None
        if hasattr(subscription, 'current_period_end') and subscription.current_period_end:
            current_period_end = datetime.fromtimestamp(subscription.current_period_end)
        
        cancel_at_period_end = False
        if hasattr(subscription, 'cancel_at_period_end'):
            cancel_at_period_end = subscription.cancel_at_period_end
        
        # Determine actual status from Stripe subscription
        actual_status = current_user.subscription_status
        if subscription.status == "trialing":
            actual_status = "trial"
        elif subscription.status == "active" and current_user.subscription_status == "trial":
            # Trial ended, update to plan type
            actual_status = current_user.subscription_plan
        
        # Get trial end date if in trial
        trial_end = None
        if hasattr(subscription, 'trial_end') and subscription.trial_end:
            trial_end = datetime.fromtimestamp(subscription.trial_end)
        
        return UserSubscriptionResponse(
            plan_type=current_user.subscription_plan,
            status=actual_status,
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
            stripe_subscription_id=subscription.id,
            message_count=current_user.message_count,
            max_messages=-1,  # Unlimited for paid plans and trials
            trial_end=trial_end if actual_status == "trial" else None
        )
    except stripe.error.InvalidRequestError as e:
        if "No such subscription" in str(e):
            # Sync database with Stripe status
            users_collection = get_users_collection()
            await users_collection.update_one(
                {"_id": ObjectId(current_user.id)},
                {"$set": {
                    "subscription_plan": "free",
                    "subscription_status": "expired",
                    "stripe_subscription_id": None,
                    "subscription_cancel_at_period_end": False,
                    "subscription_current_period_end": None,
                    "max_messages": 3,
                    "updated_at": datetime.utcnow()
                }}
            )
            return UserSubscriptionResponse(
                plan_type=PlanType.FREE,
                status=SubscriptionStatus.EXPIRED,
                current_period_end=None,
                cancel_at_period_end=False,
                stripe_subscription_id=None,
                message_count=current_user.message_count,
                max_messages=3
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")

@router.post("/webhook",
    summary="Stripe webhook handler",
    description="Handle Stripe webhook events for subscription management"
)
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events for subscription lifecycle.
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event_id = event.get('id', 'unknown')
    event_type = event['type']
    
    # Check for idempotency
    webhooks_collection = get_subscriptions_collection()
    existing_event = await webhooks_collection.find_one({"webhook_event_id": event_id})
    if existing_event:
        return {"status": "success", "message": "Event already processed"}
    
    users_collection = get_users_collection()
    
    try:
        if event["type"] == "checkout.session.completed":
            user_id = event["data"]["object"].get("metadata", {}).get("user_id")
            plan_type = event["data"]["object"].get("metadata", {}).get("plan_type")
            is_trial = event["data"]["object"].get("metadata", {}).get("is_trial", "False") == "True"
            
            if user_id and plan_type:
                checkout_session = event["data"]["object"]
                subscription_id = checkout_session.get("subscription")
                
                subscription = stripe.Subscription.retrieve(subscription_id) if subscription_id else None
                
                # Calculate trial days remaining if this is a trial
                trial_days = 0
                trial_end_date = None
                
                if is_trial and subscription and subscription.status == "trialing":
                    if hasattr(subscription, 'trial_end') and subscription.trial_end:
                        trial_end_date = datetime.fromtimestamp(subscription.trial_end, tz=timezone.utc)
                        trial_days = max(0, (trial_end_date - datetime.now(timezone.utc)).days)
                
                # Determine subscription status based on trial status
                subscription_status = "trial" if is_trial else "active"
                
                update_data = {
                    "subscription_plan": plan_type,
                    "subscription_status": subscription_status,
                    "max_messages": -1,  # Unlimited for paid plans
                    "updated_at": datetime.utcnow()
                }
                
                # Ensure message_count exists for existing users
                if "message_count" not in await users_collection.find_one({"_id": ObjectId(user_id)}, {"message_count": 1}) or {}:
                    update_data["message_count"] = 0
                
                # Handle trial-specific fields
                if is_trial:
                    update_data.update({
                        "used_trial": True,
                        "trial_active": True,
                        "trial_days": trial_days,
                        "trial_start_date": datetime.utcnow()
                    })
                    
                    if trial_end_date:
                        update_data["trial_end"] = trial_end_date
                else:
                    # Not a trial, ensure trial fields are properly set
                    update_data.update({
                        "trial_active": False,
                        "trial_days": 0
                    })
                
                if subscription:
                    update_data["stripe_subscription_id"] = subscription.id
                    
                    if hasattr(subscription, 'current_period_end') and subscription.current_period_end:
                        update_data["subscription_current_period_end"] = datetime.fromtimestamp(subscription.current_period_end)
                    
                    if hasattr(subscription, 'cancel_at_period_end'):
                        update_data["subscription_cancel_at_period_end"] = subscription.cancel_at_period_end
                
                await users_collection.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": update_data}
                )
                
                # Record webhook processing
                await webhooks_collection.insert_one({
                    "webhook_event_id": event_id,
                    "event_type": event_type,
                    "user_id": user_id,
                    "processed_at": datetime.utcnow()
                })
                
                return {"status": "success", "message": "Subscription activated"}
        
        elif event["type"] == "customer.subscription.updated":
            subscription = event["data"]["object"]
            customer_id = subscription.get("customer")
            
            if customer_id:
                user = await users_collection.find_one({"stripe_customer_id": customer_id})
                if user:
                    update_data = {
                        "subscription_cancel_at_period_end": subscription.get("cancel_at_period_end", False),
                        "updated_at": datetime.utcnow()
                    }
                    
                    # Ensure message_count exists for existing users
                    if "message_count" not in user or user.get("message_count") is None:
                        update_data["message_count"] = 0
                    
                    # Handle trial to active transition
                    if subscription.get("status") == "active" and user.get("trial_active", False):
                        # Trial ended, now active subscription - keep the same plan type
                        update_data.update({
                            "trial_active": False,
                            "trial_days": 0,
                            "trial_end": None
                        })
                    
                    # Handle ongoing trial updates
                    if subscription.get("status") == "trialing":
                        if "trial_end" in subscription and subscription["trial_end"]:
                            trial_end_date = datetime.fromtimestamp(subscription["trial_end"], tz=timezone.utc)
                            trial_days = max(0, (trial_end_date - datetime.now(timezone.utc)).days)
                            
                            update_data.update({
                                "trial_end": trial_end_date,
                                "trial_active": True,
                                "trial_days": trial_days
                            })
                    
                    if "current_period_end" in subscription:
                        update_data["subscription_current_period_end"] = datetime.fromtimestamp(subscription["current_period_end"])
                    
                    await users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$set": update_data}
                    )
                    
                    await webhooks_collection.insert_one({
                        "webhook_event_id": event_id,
                        "event_type": event_type,
                        "customer_id": customer_id,
                        "processed_at": datetime.utcnow()
                    })
                    
                    return {"status": "success", "message": "Subscription updated"}
        
        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            customer_id = subscription.get("customer")
            
            if customer_id:
                user = await users_collection.find_one({"stripe_customer_id": customer_id})
                if user:
                    # Reset to free plan with 3 messages
                    update_data = {
                        "subscription_plan": "free",
                        "subscription_status": "active",  # Free users are active, not expired
                        "max_messages": 3,  # Free users get 3 messages
                        "stripe_subscription_id": None,
                        "subscription_cancel_at_period_end": False,
                        "subscription_current_period_end": None,
                        "trial_end": None,
                        "trial_active": False,
                        "trial_days": 0,
                        "updated_at": datetime.utcnow()
                    }
                    
                    # Ensure message_count exists for existing users
                    if "message_count" not in user or user.get("message_count") is None:
                        update_data["message_count"] = 0
                    
                    await users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$set": update_data}
                    )
                    
                    await webhooks_collection.insert_one({
                        "webhook_event_id": event_id,
                        "event_type": event_type,
                        "customer_id": customer_id,
                        "processed_at": datetime.utcnow()
                    })
                    
                    return {"status": "success", "message": "Subscription cancelled"}
        
        # Record unhandled events
        await webhooks_collection.insert_one({
            "webhook_event_id": event_id,
            "event_type": event_type,
            "processed_at": datetime.utcnow(),
            "status": "unhandled" if event_type not in ["customer.created"] else "processed"
        })
        
        return {"status": "success", "message": f"Event {event_type} processed"}
    
    except Exception as e:
        return {"status": "error", "message": f"Processing failed: {str(e)}"}
        
    
@router.post("/cancel-subscription",
    response_model=CancelSubscriptionResponse,
    summary="Cancel user subscription",
    description="Cancel the current user's subscription at the end of the billing period"
)
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Cancel user's subscription. Only available for users with active subscriptions.
    """
    
    
    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found"
        )
    
    try:
        subscription = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
        
        if subscription.customer != current_user.stripe_customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to cancel this subscription"
            )
        
        params = {'cancel_at_period_end': True}
        if request.reason:
            params['cancellation_details'] = {'comment': request.reason}

        canceled_subscription = stripe.Subscription.modify(
            current_user.stripe_subscription_id,
            **params
        )
        
        users_collection = get_users_collection()
        update_data = {
            "subscription_cancel_at_period_end": True,
            "updated_at": datetime.utcnow()
        }
        
        if hasattr(canceled_subscription, 'current_period_end') and canceled_subscription.current_period_end:
            update_data["subscription_current_period_end"] = datetime.fromtimestamp(canceled_subscription.current_period_end)
        
        await users_collection.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": update_data}
        )
        
        current_period_end = None
        if hasattr(canceled_subscription, 'current_period_end') and canceled_subscription.current_period_end:
            current_period_end = datetime.fromtimestamp(canceled_subscription.current_period_end)
        
        return CancelSubscriptionResponse(
            message="Subscription will be cancelled at the end of the current billing period",
            cancel_at_period_end=True,
            current_period_end=current_period_end,
            plan_id=current_user.subscription_plan,
            status=current_user.subscription_status,
            started_at=current_user.created_at,
            expires_at=current_period_end,
            cancelled_at=datetime.utcnow()
        )
        
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stripe error: {str(e)}"
        )

class UseCreditResponse(BaseModel):
    message: str = Field(..., description="Success message")
    remaining_messages: int = Field(..., description="Remaining messages count (-1 for unlimited)")

@router.post("/use-message",
    response_model=UseCreditResponse,
    summary="Use a message credit",
    description="Increment user's message count and return remaining messages"
)
async def use_message(current_user: User = Depends(get_current_active_user)):
    """
    Use a message credit by incrementing the user's message count.
    Returns the remaining message count.
    """
    users_collection = get_users_collection()
    
    # Check if user has unlimited messages (paid subscription)
    if current_user.max_messages == -1:
        return UseCreditResponse(
            message="Message sent successfully",
            remaining_messages=-1
        )
    
    # Check if user has reached their limit
    if current_user.message_count >= current_user.max_messages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Message limit reached. Please upgrade to continue."
        )
    
    # Increment message count
    result = await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$inc": {"message_count": 1},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    new_message_count = current_user.message_count + 1
    remaining_messages = max(0, current_user.max_messages - new_message_count)
    
    return UseCreditResponse(
        message="Message sent successfully",
        remaining_messages=remaining_messages
    )
