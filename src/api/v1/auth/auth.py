from fastapi import APIRouter, Depends, HTTPException, status, Form, Path
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Dict, Any, List
from bson import ObjectId

from ....models.users import User, UserCreate, UserLogin, UserResponse, UserType, PlanType, LoginRequest, AccountStatus
from ....database import get_users_collection
from ....auth.utils import (
    get_password_hash,
    authenticate_user_by_username_or_email,
    get_user_by_email,
    get_user_by_username,
    get_user_by_id,
    update_user_login,
    verify_password,
)
from ....auth.jwt import create_access_token, create_refresh_token, verify_token
from ....auth.dependencies import get_current_active_user
from ....services.account_status import AccountStatusManager
from ....config import settings

router = APIRouter()

# Utility to derive frontend role from backend user_type
def derive_role(user_type: str | UserType | None) -> str:
    if not user_type:
        return "student"
    # Accept both enum and raw string
    value = user_type.value if isinstance(user_type, UserType) else str(user_type)
    return "admin" if value in ("admin", "super_admin") else "student"

# Response models for OpenAPI documentation
class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token", example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    refresh_token: str = Field(..., description="Refresh token for getting new access tokens", example="abc123def456...")
    token_type: str = Field(default="bearer", description="Token type", example="bearer")
    user: UserResponse = Field(..., description="User information")

class RefreshTokenResponse(BaseModel):
    access_token: str = Field(..., description="New JWT access token", example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    token_type: str = Field(default="bearer", description="Token type", example="bearer")

class SignupResponse(BaseModel):
    message: str = Field(..., description="Success message", example="User registration successful. Your account is pending approval.")
    user: UserResponse = Field(..., description="Created user information")

class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message", example="Operation completed successfully")

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token", example="abc123def456...")

@router.post("/signup", 
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
    description="Register a new user with email and password. Account will be created with 'requested' status and require admin approval before login.",
    responses={
        201: {
            "description": "User registration successful, pending approval",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User registration successful. Your account is pending approval.",
                        "user": {
                            "id": "507f1f77bcf86cd799439011",
                            "email": "john@example.com",
                            "first_name": "John",
                            "last_name": "Doe",
                            "is_active": False,
                            "account_status": "requested",
                            "subscription_plan": "free",
                            "subscription_status": "active",
                            "user_type": "customer",
                            "created_at": "2025-07-11T10:30:00Z"
                        }
                    }
                }
            }
        },
        400: {"description": "Email already registered or validation error"},
        422: {"description": "Validation error - invalid input data"}
    }
)
async def signup(user_data: UserCreate):
    """Register a new user and return auth data with correct role derived from user_type."""
    users_collection = get_users_collection()

    # Validation
    if not user_data.email or not user_data.email.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address is required")
    if not user_data.password or len(user_data.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters long")

    existing_user = await get_user_by_email(user_data.email.lower().strip())
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email address already exists")

    # Core account setup
    now = datetime.utcnow()
    hashed_password = get_password_hash(user_data.password)
    subscription_plan = "free"
    subscription_status = "active"

    # Basic role determination (extend with your own logic)
    user_type: str = "customer"
    role: str = derive_role(user_type)
    admin_emails = ["admin@therapy.com", "admin@example.com"]
    if user_data.email.lower().strip() in admin_emails:
        user_type = "admin"
        role = derive_role(user_type)

    import uuid
    user_doc = {
        "uuid": str(uuid.uuid4()),
        "email": user_data.email.lower().strip(),
        "hashed_password": hashed_password,
        "first_name": user_data.first_name.strip() if user_data.first_name else None,
        "last_name": user_data.last_name.strip() if user_data.last_name else None,
        "name": (user_data.first_name.strip() if user_data.first_name else user_data.email.split('@')[0]),
        "is_active": False,  # Set to False initially, will be True when activated
        "is_superuser": user_type == "admin",
        "account_status": AccountStatus.REQUESTED.value,  # Set initial status as requested
        "status_changed_at": now,
        "status_changed_by": None,  # No admin changed it initially
        "subscription_plan": subscription_plan,
        "subscription_status": subscription_status,
        "trial_start_date": None,
        "subscription_expiry": None,
        "is_anonymous": False,
        "display_name": None,
        "used_trial": False,
        "trial_active": False,
        "trial_days": 0,
        "message_count": 0,
        "max_messages": -1,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "subscription_cancel_at_period_end": False,
        "subscription_current_period_end": None,
        "user_type": user_type,
        "role": role,
        "university": None,
        "year": None,
        "created_at": now,
        "updated_at": now,
    }

    result = await users_collection.insert_one(user_doc)
    if not result.inserted_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create account. Please try again.")

    # Do not create access token or auto-login - requirement 2.1
    created_user = await users_collection.find_one({"_id": result.inserted_id})
    if not created_user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account created but failed to retrieve user data. Please contact support.")

    created_user["_id"] = str(created_user["_id"])
    created_user["id"] = created_user["_id"]
    created_user["createdAt"] = created_user["created_at"]
    created_user["subscription"] = created_user["subscription_plan"]
    # Enforce role derivation from user_type (safety)
    created_user["role"] = derive_role(created_user.get("user_type"))

    user_response = UserResponse(**created_user)
    return {
        "message": "User registration successful. Your account is pending approval.",
        "user": user_response.dict(),
    }

@router.post("/login", 
    response_model=TokenResponse,
    summary="Login user",
    description="Authenticate user with email and password. Only users with 'activated' status can login.",
    responses={
        200: {
            "description": "Login successful"
        },
        401: {
            "description": "Authentication failed or account not activated",
            "content": {
                "application/json": {
                    "examples": {
                        "pending_approval": {
                            "summary": "Account pending approval",
                            "value": {"detail": "Your account is pending approval. Please wait for an admin to activate your account."}
                        },
                        "rejected": {
                            "summary": "Account rejected",
                            "value": {"detail": "Your account has been rejected. Please contact support if you believe this is an error."}
                        },
                        "deactivated": {
                            "summary": "Account deactivated",
                            "value": {"detail": "Your account has been deactivated. Please contact support."}
                        },
                        "refused": {
                            "summary": "Access refused",
                            "value": {"detail": "Access to your account has been refused."}
                        }
                    }
                }
            }
        },
        400: {"description": "Validation error - missing required fields"},
        422: {"description": "Validation error - invalid input data"}
    }
)
async def login(request: LoginRequest):
    """Authenticate user and return tokens. Handles nuanced account status and inactive flag."""
    # Basic validation
    if not request.username or not request.username.strip():
        raise HTTPException(status_code=400, detail="Email address is required")
    if not request.password:
        raise HTTPException(status_code=400, detail="Password is required")

    email = request.username.lower().strip()
    user_record = await get_user_by_email(email)
    if not user_record:
        # Generic to avoid user enumeration
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # Account status messages
    status_messages = {
        AccountStatus.REQUESTED: "Your account is pending approval. Please wait for an admin to activate your account.",
        AccountStatus.REJECTED: "Your account has been rejected. Please contact support if you believe this is an error.",
        AccountStatus.DEACTIVATED: "Your account has been deactivated. Please contact support.",
        AccountStatus.REFUSED: "Access to your account has been refused.",
    }

    # If not activated, block before password check to avoid leaking activation state except for requested status
    if user_record.account_status != AccountStatus.ACTIVATED:
        raise HTTPException(status_code=401, detail=status_messages.get(user_record.account_status, "Account not active"))

    # Verify password manually (avoid is_active short-circuit in helper)
    if not verify_password(request.password, user_record.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    users_collection = get_users_collection()

    # Auto-heal legacy records: activated status but is_active False
    if not user_record.is_active:
        try:
            await users_collection.update_one({"_id": ObjectId(user_record.id)}, {"$set": {"is_active": True}})
            user_record.is_active = True  # mutate local model
        except Exception:
            pass

    # Still inactive? Then block.
    if not user_record.is_active:
        raise HTTPException(status_code=401, detail="Your account is not active. Please contact support.")

    # Issue tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token({"sub": str(user_record.id)}, expires_delta=access_token_expires)
    refresh_token_value, refresh_expires = create_refresh_token()

    # Persist refresh token + last login
    update_res = await users_collection.update_one(
        {"_id": ObjectId(user_record.id)},
        {"$set": {"refresh_token": refresh_token_value, "refresh_token_expires_at": refresh_expires, "last_login": datetime.utcnow()}}
    )
    if update_res.matched_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update login metadata")

    # Build user response dict
    user_dict = user_record.dict()
    user_dict["id"] = user_dict.get("id", user_dict.get("_id"))
    user_dict["createdAt"] = user_dict.get("created_at")
    user_dict["subscription"] = user_dict.get("subscription_plan", "free")
    derived_role = derive_role(user_dict.get("user_type"))
    if user_dict.get("role") != derived_role:
        user_dict["role"] = derived_role
        try:
            await users_collection.update_one({"_id": ObjectId(user_record.id)}, {"$set": {"role": derived_role}})
        except Exception:
            pass

    user_response = UserResponse(**user_dict)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token_value,
        "token_type": "bearer",
        "user": user_response.dict()
    }

@router.post("/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token",
    description="Get a new access token using a valid refresh token",
    responses={
        200: {
            "description": "New access token generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer"
                    }
                }
            }
        },
        401: {"description": "Invalid or expired refresh token"},
        400: {"description": "Missing refresh token"},
        404: {"description": "User not found"}
    }
)
async def refresh_token(refresh_request: RefreshTokenRequest):
    """
    Generate a new access token using a valid refresh token.
    
    - **refresh_token**: Valid refresh token received during login
    
    Returns a new JWT access token.
    """
    try:
        # Validate input
        if not refresh_request.refresh_token or not refresh_request.refresh_token.strip():
            print("❌ No refresh token provided")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refresh token is required"
            )
        
        print(f"🔄 Attempting to refresh token: {refresh_request.refresh_token[:20]}...")
        
        users_collection = get_users_collection()
        
        # Find user with the provided refresh token
        user_data = await users_collection.find_one({
            "refresh_token": refresh_request.refresh_token,
            "refresh_token_expires_at": {"$gt": datetime.utcnow()}
        })
        
        if not user_data:
            print("❌ No valid user found with refresh token")
            
            # Check if token exists but is expired
            expired_user = await users_collection.find_one({
                "refresh_token": refresh_request.refresh_token
            })
            
            if expired_user:
                print(f"⏰ Refresh token expired for user: {expired_user.get('email', 'unknown')}")
                print(f"Token expires at: {expired_user.get('refresh_token_expires_at')}")
                print(f"Current time: {datetime.utcnow()}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has expired. Please log in again."
                )
            else:
                print("❌ Refresh token not found in database")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token. Please log in again."
                )
        
        print(f"✅ Found user for refresh: {user_data.get('email', 'unknown')}")
        
        # Check account status for refresh token
        account_status = AccountStatus(user_data.get("account_status", AccountStatus.REQUESTED.value))
        if account_status != AccountStatus.ACTIVATED:
            print(f"❌ User account status is {account_status.value}: {user_data.get('email', 'unknown')}")
            status_message = AccountStatusManager.get_status_message(account_status)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=status_message
            )
        
        # Create new access token
        access_token = create_access_token(data={"sub": str(user_data["_id"])})
        
        print(f"✅ New access token created for user: {user_data.get('email', 'unknown')}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"❌ Unexpected error in refresh_token: {e}")
        # Handle unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while refreshing your token. Please log in again."
        )

@router.post("/logout",
    response_model=MessageResponse,
    summary="Logout user",
    description="Logout the current user and invalidate their refresh token",
    responses={
        200: {
            "description": "Logout successful",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Successfully logged out"
                    }
                }
            }
        },
        401: {"description": "Authentication required"}
    }
)
async def logout(current_user: User = Depends(get_current_active_user)):
    """
    Logout user and invalidate refresh token.
    
    This will clear the refresh token from the database, making it invalid for future use.
    The client should also clear the access token from storage.
    """
    users_collection = get_users_collection()
    
    # Clear the refresh token from the user's record
    await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$unset": {
                "refresh_token": "",
                "refresh_token_expires_at": ""
            }
        }
    )
    
    return {"message": "Successfully logged out"}

@router.get("/me", 
    response_model=UserResponse,
    summary="Get current user information",
    description="Get authenticated user's profile information and current credit status",
    responses={
        200: {
            "description": "User information retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "is_active": True,
                        "subscription_plan": "free",
                        "credits": 1,
                        "user_type": "customer",
                        "created_at": "2025-07-11T10:30:00Z",
                        "last_login": "2025-07-11T12:45:00Z"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        400: {"description": "Inactive user"}
    }
)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current user information.
    
    Returns user profile information.
    """
    # Get fresh user data from database to ensure we have the latest data
    fresh_user = await get_user_by_id(current_user.id)
    if not fresh_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    # Ensure role consistency on /me endpoint as well
    fresh_dict = fresh_user.dict()
    derived_role = derive_role(fresh_dict.get("user_type"))
    if fresh_dict.get("role") != derived_role:
        fresh_dict["role"] = derived_role
        try:
            users_collection = get_users_collection()
            await users_collection.update_one({"_id": ObjectId(fresh_user.id)}, {"$set": {"role": derived_role}})
        except Exception:
            pass
    user_response = UserResponse(**fresh_dict)
    return user_response
