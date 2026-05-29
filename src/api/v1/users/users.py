from fastapi import APIRouter, Depends, HTTPException, status, Path
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId
from pydantic import GetJsonSchemaHandler
from pydantic_core import CoreSchema

from ....models.users import User, UserCreate, UserResponse, UserType, PlanType, SubscriptionStatus, AccountStatus

from ....database import get_users_collection
from ....auth.utils import (
    get_password_hash, 
    get_user_by_email,
    get_user_by_id
)
from ....auth.dependencies import get_current_active_user, require_admin, require_moderator
from ....auth.permissions import PermissionChecker

router = APIRouter()

# Account Status Management Service
class AccountStatusManager:
    """Service for managing user account status transitions and validation"""
    
    # Define allowed status transitions
    ALLOWED_TRANSITIONS = {
        AccountStatus.REQUESTED: [AccountStatus.ACTIVATED, AccountStatus.REJECTED, AccountStatus.REFUSED],
        AccountStatus.ACTIVATED: [AccountStatus.DEACTIVATED],
        AccountStatus.DEACTIVATED: [AccountStatus.ACTIVATED],
        AccountStatus.REJECTED: [],  # Final status
        AccountStatus.REFUSED: []    # Final status
    }
    
    @staticmethod
    def can_transition(from_status: AccountStatus, to_status: AccountStatus) -> bool:
        """Check if a status transition is allowed"""
        return to_status in AccountStatusManager.ALLOWED_TRANSITIONS.get(from_status, [])
    
    @staticmethod
    async def update_user_status(user_id: str, new_status: AccountStatus, admin_id: str, reason: Optional[str] = None) -> bool:
        """Update user account status with validation and audit logging"""
        users_collection = get_users_collection()
        
        # Get current user
        user = await get_user_by_id(user_id)
        if not user:
            return False
        
        # Validate transition
        if not AccountStatusManager.can_transition(user.account_status, new_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from {user.account_status} to {new_status}"
            )
        
        # Update user status
        update_data = {
            "account_status": new_status.value,
            "status_changed_at": datetime.utcnow(),
            "status_changed_by": admin_id,
            "updated_at": datetime.utcnow()
        }
        
        # Also update is_active based on status
        if new_status in [AccountStatus.ACTIVATED]:
            update_data["is_active"] = True
        elif new_status in [AccountStatus.DEACTIVATED, AccountStatus.REJECTED, AccountStatus.REFUSED]:
            update_data["is_active"] = False
        else:  # REQUESTED
            update_data["is_active"] = False
        
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    @staticmethod
    async def get_pending_requests_count() -> int:
        """Get count of users with requested status"""
        users_collection = get_users_collection()
        count = await users_collection.count_documents({"account_status": AccountStatus.REQUESTED.value})
        return count
    
    @staticmethod
    def get_status_message(account_status: AccountStatus) -> str:
        """Get user-friendly message for account status"""
        messages = {
            AccountStatus.REQUESTED: "Your account is pending approval. Please wait for an admin to activate your account.",
            AccountStatus.REJECTED: "Your account has been rejected. Please contact support if you believe this is an error.",
            AccountStatus.REFUSED: "Access to your account has been refused.",
            AccountStatus.DEACTIVATED: "Your account has been deactivated. Please contact support.",
            AccountStatus.ACTIVATED: "Your account is active."
        }
        return messages.get(account_status, "Unknown account status.")

# Response models for OpenAPI documentation
class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message", example="Operation completed successfully")

class UserListResponse(BaseModel):
    users: List[UserResponse] = Field(..., description="List of users")

class UserPermissionsResponse(BaseModel):
    user_type: UserType = Field(..., description="User type", example=UserType.CUSTOMER)
    permissions: Dict[str, bool] = Field(..., description="User permissions")

class UserDetailResponse(BaseModel):
    user: UserResponse = Field(..., description="User information")
    permissions: Dict[str, bool] = Field(..., description="User permissions")

class AdminCreateUserResponse(BaseModel):
    message: str = Field(..., description="Success message", example="User created successfully with role: moderator")
    user: UserResponse = Field(..., description="Created user information")

class PendingRequestsResponse(BaseModel):
    pending_requests: int = Field(..., description="Number of users with requested status", example=5)

class StatusStatisticsResponse(BaseModel):
    requested: int = Field(..., description="Number of users with requested status", example=5)
    activated: int = Field(..., description="Number of users with activated status", example=25)
    deactivated: int = Field(..., description="Number of users with deactivated status", example=2)
    rejected: int = Field(..., description="Number of users with rejected status", example=1)
    refused: int = Field(..., description="Number of users with refused status", example=0)

# Request models
class UpdateUserRoleRequest(BaseModel):
    new_role: UserType = Field(..., description="New role to assign", example=UserType.MODERATOR)

class UpdateUserStatusRequest(BaseModel):
    is_active: bool = Field(..., description="New active status", example=True)

class UpdateAccountStatusRequest(BaseModel):
    new_status: AccountStatus = Field(..., description="New account status", example=AccountStatus.ACTIVATED)
    reason: Optional[str] = Field(None, description="Optional reason for status change", example="Approved by admin")

class UpdatePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6, description="Current password", example="currentpassword123")
    new_password: str = Field(..., min_length=6, description="New password (minimum 6 characters)", example="newpassword123")

class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, description="New password (minimum 6 characters)", example="newsecurepass1")
    confirm_password: str = Field(..., min_length=6, description="Repeat new password for confirmation", example="newsecurepass1")

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Email of account to request password reset")

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name") 
    display_name: Optional[str] = Field(None, description="Display name for anonymity")
    university: Optional[str] = Field(None, description="University name")
    year: Optional[int] = Field(None, description="Academic year", ge=1, le=6)

class ToggleAnonymousRequest(BaseModel):
    enabled: bool = Field(..., description="Enable or disable anonymous mode")

@router.get("/users",
    response_model=UserListResponse,
    summary="Get all users",
    description="Retrieve list of all users with optional status filtering (moderator+ access required)",
    responses={
        200: {
            "description": "Users retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "users": [
                            {
                                "id": "507f1f77bcf86cd799439011",
                                "name": "John Doe",
                                "email": "john@example.com",
                                "is_active": True,
                                "subscription_plan": "free",
                                "credits": 2,
                                "user_type": "customer",
                                "created_at": "2025-07-11T10:30:00Z",
                                "last_login": "2025-07-11T12:45:00Z"
                            }
                        ]
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Moderator permissions or higher required"}
    }
)
async def get_users(
    status: Optional[AccountStatus] = None,
    current_user: User = Depends(require_moderator)
):
    """
    Retrieve a list of users (moderator+ only).
    
    - **status**: Optional filter by account status
    
    Returns all users with sensitive information (passwords, tokens) excluded.
    Only accessible by moderators, admins, and super admins.
    """
    users_collection = get_users_collection()
    
    # Build query filter
    query_filter = {}
    if status:
        query_filter["account_status"] = status.value
    
    users_cursor = users_collection.find(query_filter, {"hashed_password": 0, "refresh_token": 0})
    users = []
    async for user_doc in users_cursor:
        # Convert ObjectId to string for Pydantic model
        user_doc["_id"] = str(user_doc["_id"])
        
        # Compute name field from first_name and last_name for frontend compatibility
        if user_doc.get("first_name") and user_doc.get("last_name"):
            user_doc["name"] = f"{user_doc['first_name']} {user_doc['last_name']}"
        elif user_doc.get("first_name"):
            user_doc["name"] = user_doc["first_name"]
        elif user_doc.get("last_name"):
            user_doc["name"] = user_doc["last_name"]
        else:
            user_doc["name"] = user_doc.get("email", "").split("@")[0]
        
        try:
            user_response = UserResponse(**user_doc)
            users.append(user_response.dict(by_alias=False))
        except Exception:
            continue
    
    return {"users": users}

@router.post("/admin/create-user",
    response_model=AdminCreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user (Admin)",
    description="Create a new user with specified role (admin+ access required)",
    responses={
        201: {
            "description": "User created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User created successfully with role: moderator",
                        "user": {
                            "id": "507f1f77bcf86cd799439011",
                            "name": "Jane Moderator",
                            "email": "jane@example.com",
                            "is_active": True,
                            "subscription_plan": "free",
                            "credits": 2,
                            "user_type": "moderator",
                            "created_at": "2025-07-11T10:30:00Z",
                            "last_login": None
                        }
                    }
                }
            }
        },
        400: {"description": "Email or username already registered"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin permissions required or insufficient role permissions"}
    }
)
async def create_user_by_admin(
    user_data: UserCreate,
    user_type: UserType = UserType.CUSTOMER,
    current_user: User = Depends(require_admin)
):
    """
    Create a new user (admin only).
    
    - **user_data**: User creation data (username, name, email, password)
    - **user_type**: Role to assign to the new user
    
    **Permission Rules:**
    - Admins can create customers and moderators
    - Only super admins can create admin or super admin users
    """
    users_collection = get_users_collection()
    
    # Check if email already exists
    existing_user = await get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Note: We're using email as the username in this system
    # No need to check for separate username since email is unique
    
    # Only super admin can create admin/super admin users
    if user_type in [UserType.ADMIN, UserType.SUPER_ADMIN] and current_user.user_type != UserType.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create admin users"
        )
    
    # Hash the password
    hashed_password = get_password_hash(user_data.password)
    
    # Create user document
    user_doc = {
        "email": user_data.email,
        "hashed_password": hashed_password,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "is_active": True,
        "subscription_plan": PlanType.FREE.value,
        "subscription_status": SubscriptionStatus.ACTIVE.value,
        "message_count": 0,
        "max_messages": 3,  # All new users get 3 free messages
        "used_trial": False,
        "trial_active": False,
        "trial_days": 0,
        "user_type": user_type.value,
    # Initialize account status as requested (pending approval workflow)
    "account_status": AccountStatus.REQUESTED.value,
    "status_changed_at": datetime.utcnow(),
    "status_changed_by": current_user.id,  # Admin creating the account
        "stripe_customer_id": None,  # Initialize as null
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    # Insert user into database
    result = await users_collection.insert_one(user_doc)
    
    # Get the created user
    created_user = await users_collection.find_one({"_id": result.inserted_id})
    # Convert ObjectId to string for Pydantic model
    created_user["_id"] = str(created_user["_id"])
    
    # Compute name field from first_name and last_name for frontend compatibility
    if created_user.get("first_name") and created_user.get("last_name"):
        created_user["name"] = f"{created_user['first_name']} {created_user['last_name']}"
    elif created_user.get("first_name"):
        created_user["name"] = created_user["first_name"]
    elif created_user.get("last_name"):
        created_user["name"] = created_user["last_name"]
    else:
        created_user["name"] = created_user.get("email", "").split("@")[0]
    
    user_response = UserResponse(**created_user)
    
    return {
        "message": f"User created successfully with role: {user_type.value}",
        "user": user_response.dict(by_alias=False)
    }

@router.put("/admin/users/{user_id}/role",
    response_model=MessageResponse,
    summary="Update user role (Admin)",
    description="Change a user's role/type (admin+ access required)",
    responses={
        200: {
            "description": "User role updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User role updated to moderator"
                    }
                }
            }
        },
        404: {"description": "User not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions to modify this user"}
    }
)
async def update_user_role(
    role_data: UpdateUserRoleRequest,
    user_id: str = Path(..., description="User ID to update", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(require_admin)
):
    """
    Update user role (admin only).
    
    **Permission Rules:**
    - Admins can modify customers and moderators
    - Only super admins can assign admin/super admin roles
    - Users cannot modify users at their level or above
    """
    users_collection = get_users_collection()
    
    # Get target user
    target_user = await get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if current user can manage target user
    if not PermissionChecker.can_manage_user(current_user, target_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to modify this user"
        )
    
    # Only super admin can create/modify admin/super admin users
    if role_data.new_role in [UserType.ADMIN, UserType.SUPER_ADMIN] and current_user.user_type != UserType.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can assign admin roles"
        )
    
    # Update user role
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"user_type": role_data.new_role.value, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": f"User role updated to {role_data.new_role.value}"}

@router.put("/admin/users/{user_id}/status",
    response_model=MessageResponse,
    summary="Update user status (Admin)",
    description="Activate or deactivate a user account (admin+ access required)",
    responses={
        200: {
            "description": "User status updated successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "activated": {"value": {"message": "User activated successfully"}},
                        "deactivated": {"value": {"message": "User deactivated successfully"}}
                    }
                }
            }
        },
        404: {"description": "User not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions or cannot deactivate super admin"}
    }
)
async def update_user_status(
    status_data: UpdateUserStatusRequest,
    user_id: str = Path(..., description="User ID to update", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(require_admin)
):
    """
    Update user active status (admin only).
    
    **Rules:**
    - Cannot deactivate super admin accounts
    - Admins can only modify users below their level
    """
    users_collection = get_users_collection()
    
    # Get target user
    target_user = await get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if current user can manage target user
    if not PermissionChecker.can_manage_user(current_user, target_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to modify this user"
        )
    
    # Prevent deactivating super admin accounts
    if target_user.user_type == UserType.SUPER_ADMIN and not status_data.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate super admin accounts"
        )
    
    # Update user status
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_active": status_data.is_active, "updated_at": datetime.utcnow()}}
    )
    
    status_text = "activated" if status_data.is_active else "deactivated"
    return {"message": f"User {status_text} successfully"}

@router.put("/admin/users/{user_id}/account-status",
    response_model=MessageResponse,
    summary="Update user account status (Admin)",
    description="Update a user's account status with validation and audit logging (admin+ access required)",
    responses={
        200: {
            "description": "Account status updated successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "activated": {"value": {"message": "User account status updated to activated"}},
                        "rejected": {"value": {"message": "User account status updated to rejected"}},
                        "deactivated": {"value": {"message": "User account status updated to deactivated"}}
                    }
                }
            }
        },
        400: {"description": "Invalid status transition"},
        404: {"description": "User not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions"}
    }
)
async def update_user_account_status(
    status_data: UpdateAccountStatusRequest,
    user_id: str = Path(..., description="User ID to update", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(require_admin)
):
    """
    Update user account status (admin only).
    
    **Status Transitions (updated):**
    - requested → activated, rejected, refused
    - activated → deactivated
    - deactivated → activated
    - rejected → activated (reactivation allowed)
    - refused → activated (reactivation allowed)
    
    **Rules:**
    - Only admins can change account status
    - All status changes are logged with admin ID and timestamp
    - Invalid transitions are rejected with detailed error messages
    - Reactivation from rejected/refused is now supported (policy update)
    """
    from ....services.account_status import AccountStatusManager
    
    # Get target user to check permissions
    target_user = await get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if current user can manage target user
    if not PermissionChecker.can_manage_user(current_user, target_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to modify this user"
        )
    
    # Update account status using the service
    try:
        success = await AccountStatusManager.update_user_status(
            user_id=user_id,
            new_status=status_data.new_status,
            admin_id=current_user.id,
            reason=status_data.reason
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update account status"
            )
        
        return {"message": f"User account status updated to {status_data.new_status.value}"}
        
    except HTTPException:
        # Re-raise HTTP exceptions from the service
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating account status"
        )

@router.get("/admin/pending-requests",
    response_model=PendingRequestsResponse,
    summary="Get pending user requests count",
    description="Get count of users with 'requested' status for admin dashboard (admin+ access required)",
    responses={
        200: {
            "description": "Pending requests count retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "pending_requests": 5
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin permissions required"}
    }
)
async def get_pending_requests_count(current_user: User = Depends(require_admin)):
    """
    Get count of pending user requests (admin only).
    
    Returns the number of users with 'requested' account status.
    Used by admin dashboard to show pending approval notifications.
    """
    from ....services.account_status import AccountStatusManager
    
    count = await AccountStatusManager.get_pending_requests_count()
    return {"pending_requests": count}

@router.get("/admin/status-statistics",
    response_model=StatusStatisticsResponse,
    summary="Get user status statistics",
    description="Get count of users by account status for admin dashboard (admin+ access required)",
    responses={
        200: {
            "description": "Status statistics retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "requested": 5,
                        "activated": 25,
                        "deactivated": 2,
                        "rejected": 1,
                        "refused": 0
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Admin permissions required"}
    }
)
async def get_status_statistics(current_user: User = Depends(require_admin)):
    """
    Get user account status statistics (admin only).
    
    Returns count of users for each account status.
    Used by admin dashboard for overview and analytics.
    """
    from ....services.account_status import AccountStatusManager
    
    stats = await AccountStatusManager.get_status_statistics()
    return {
        "requested": stats.get("requested", 0),
        "activated": stats.get("activated", 0),
        "deactivated": stats.get("deactivated", 0),
        "rejected": stats.get("rejected", 0),
        "refused": stats.get("refused", 0)
    }

@router.get("/admin/users/{user_id}",
    response_model=UserDetailResponse,
    summary="Get user details (Admin)",
    description="Get detailed user information including permissions (moderator+ access required)",
    responses={
        200: {
            "description": "User details retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "user": {
                            "id": "507f1f77bcf86cd799439011",
                            "name": "John Doe",
                            "email": "john@example.com",
                            "is_active": True,
                            "subscription_plan": "pro_monthly",
                            "credits": -1,
                            "user_type": "customer",
                            "created_at": "2025-07-11T10:30:00Z",
                            "last_login": "2025-07-11T12:45:00Z"
                        },
                        "permissions": {
                            "can_create_ideas": True,
                            "can_view_own_data": True,
                            "can_subscribe": True,
                            "can_export_pdf": True,
                            "can_view_analytics": False,
                            "can_manage_users": False,
                            "can_moderate_content": False,
                            "can_access_admin_panel": False
                        }
                    }
                }
            }
        },
        404: {"description": "User not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions to view this user"}
    }
)
async def get_user_details(
    user_id: str = Path(..., description="User ID to retrieve", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(require_moderator)
):
    """
    Get detailed user information (moderator+ only).
    
    Returns user information along with their permission set.
    Moderators and admins can only view users they can manage.
    """
    target_user = await get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if current user can view target user
    if not PermissionChecker.can_manage_user(current_user, target_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view this user"
        )
    
    # Convert to dict and compute name field
    user_dict = target_user.dict()
    if user_dict.get("first_name") and user_dict.get("last_name"):
        user_dict["name"] = f"{user_dict['first_name']} {user_dict['last_name']}"
    elif user_dict.get("first_name"):
        user_dict["name"] = user_dict["first_name"]
    elif user_dict.get("last_name"):
        user_dict["name"] = user_dict["last_name"]
    else:
        user_dict["name"] = user_dict.get("email", "").split("@")[0]
    
    user_response = UserResponse(**user_dict)
    permissions = PermissionChecker.get_user_permissions(target_user.user_type)
    
    return {
        "user": user_response.dict(by_alias=False),
        "permissions": permissions
    }

@router.get("/permissions",
    response_model=UserPermissionsResponse,
    summary="Get user permissions",
    description="Get current user's role and permission set",
    responses={
        200: {
            "description": "Permissions retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "customer": {
                            "value": {
                                "user_type": "customer",
                                "permissions": {
                                    "can_create_ideas": True,
                                    "can_view_own_data": True,
                                    "can_subscribe": True,
                                    "can_export_pdf": False,
                                    "can_view_analytics": False,
                                    "can_manage_users": False,
                                    "can_moderate_content": False,
                                    "can_access_admin_panel": False
                                }
                            }
                        },
                        "admin": {
                            "value": {
                                "user_type": "admin",
                                "permissions": {
                                    "can_create_ideas": True,
                                    "can_view_own_data": True,
                                    "can_subscribe": True,
                                    "can_export_pdf": True,
                                    "can_view_analytics": True,
                                    "can_manage_users": True,
                                    "can_moderate_content": True,
                                    "can_access_admin_panel": True
                                }
                            }
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"}
    }
)
async def get_my_permissions(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's permissions.
    
    Returns the user's role and a detailed breakdown of their permissions.
    Useful for frontend to determine what features to show/hide.
    """
    permissions = PermissionChecker.get_user_permissions(current_user.user_type)
    return {
        "user_type": current_user.user_type,
        "permissions": permissions
    }

@router.put("/update-password",
    response_model=MessageResponse,
    summary="Update user password",
    description="Update current user's password",
    responses={
        200: {
            "description": "Password updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Password updated successfully"
                    }
                }
            }
        },
        400: {
            "description": "Invalid current password or validation error"
        },
        401: {"description": "Authentication required"}
    }
)
async def update_password(
    request: UpdatePasswordRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update user's password.
    
    Requires the current password for verification and a new password.
    The new password must be at least 6 characters long.
    """
    from ....auth.utils import verify_password
    
    users_collection = get_users_collection()
    
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Hash the new password
    new_hashed_password = get_password_hash(request.new_password)
    
    # Update password in database
    result = await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$set": {
                "hashed_password": new_hashed_password,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "Password updated successfully"}

@router.post("/forgot-password",
    response_model=MessageResponse,
    summary="Request password reset (user)",
    description="User initiates an admin-mediated password reset request. Marks reset_request flag for admins.",
    responses={
        200: {"description": "Reset request recorded"},
        404: {"description": "User not found"}
    }
)
async def forgot_password(request: ForgotPasswordRequest):
    """Mark a user's account with a password reset request flag.

    This does NOT send email nor expose whether an account exists beyond generic message.
    Admins can later reset password without old password via admin endpoint.
    """
    users_collection = get_users_collection()
    user_doc = await users_collection.find_one({"email": request.email.lower()})
    if user_doc:
        await users_collection.update_one(
            {"_id": user_doc["_id"]},
            {"$set": {"reset_request": True, "reset_requested_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
    # Always respond success to avoid enumeration
    return {"message": "If the email exists, an admin has been notified of your reset request."}

@router.post("/admin/users/{user_id}/reset-password",
    response_model=MessageResponse,
    summary="Admin reset user password",
    description="Admin resets a user's password after a reset request. Does not require current password.",
    responses={
        200: {"description": "Password reset successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "User not found"}
    }
)
async def admin_reset_user_password(
    request: AdminResetPasswordRequest,
    user_id: str = Path(..., description="User ID to reset password for"),
    current_user: User = Depends(require_admin)
):
    from ....auth.utils import get_password_hash
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    users_collection = get_users_collection()
    target_user = await get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    # Permission: ensure admin can manage this user
    if not PermissionChecker.can_manage_user(current_user, target_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions to modify this user")
    hashed = get_password_hash(request.new_password)
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"hashed_password": hashed, "reset_request": False, "updated_at": datetime.utcnow()}}
    )
    return {"message": "Password reset successfully"}

@router.get("/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Get authenticated user's profile information",
    responses={
        200: {"description": "User profile retrieved successfully"},
        401: {"description": "Authentication required"}
    }
)
async def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's profile information.
    
    Returns complete user profile with subscription and usage information.
    """
    # Convert to dict and compute name field
    user_dict = current_user.dict()
    if user_dict.get("first_name") and user_dict.get("last_name"):
        user_dict["name"] = f"{user_dict['first_name']} {user_dict['last_name']}"
    elif user_dict.get("first_name"):
        user_dict["name"] = user_dict["first_name"]
    elif user_dict.get("last_name"):
        user_dict["name"] = user_dict["last_name"]
    else:
        user_dict["name"] = user_dict.get("email", "").split("@")[0]
    
    return UserResponse(**user_dict)

@router.put("/me",
    response_model=UserResponse,
    summary="Update user profile",
    description="Update current user's profile information",
    responses={
        200: {"description": "Profile updated successfully"},
        401: {"description": "Authentication required"}
    }
)
async def update_user_profile(
    profile_data: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update user's profile information.
    
    - **first_name**: Optional first name
    - **last_name**: Optional last name  
    - **display_name**: Optional display name for anonymous mode
    """
    users_collection = get_users_collection()
    
    update_data = {"updated_at": datetime.utcnow()}
    
    if profile_data.first_name is not None:
        update_data["first_name"] = profile_data.first_name
    if profile_data.last_name is not None:
        update_data["last_name"] = profile_data.last_name
    if profile_data.display_name is not None:
        update_data["display_name"] = profile_data.display_name
    if profile_data.university is not None:
        update_data["university"] = profile_data.university
    if profile_data.year is not None:
        update_data["year"] = profile_data.year
    
    result = await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get updated user
    updated_user = await users_collection.find_one({"_id": ObjectId(current_user.id)})
    updated_user["_id"] = str(updated_user["_id"])
    
    # Compute name field from first_name and last_name for frontend compatibility
    if updated_user.get("first_name") and updated_user.get("last_name"):
        updated_user["name"] = f"{updated_user['first_name']} {updated_user['last_name']}"
    elif updated_user.get("first_name"):
        updated_user["name"] = updated_user["first_name"]
    elif updated_user.get("last_name"):
        updated_user["name"] = updated_user["last_name"]
    else:
        updated_user["name"] = updated_user.get("email", "").split("@")[0]
    
    return UserResponse(**updated_user)

@router.post("/toggle-anonymous",
    response_model=MessageResponse,
    summary="Toggle anonymous mode",
    description="Enable or disable anonymous mode for the user",
    responses={
        200: {"description": "Anonymous mode toggled successfully"},
        403: {"description": "Anonymous mode requires subscription for adults"},
        401: {"description": "Authentication required"}
    }
)
async def toggle_anonymous_mode(
    request: ToggleAnonymousRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Toggle anonymous mode for the user.
    
    - Teen users: Can enable/disable freely
    - Adult users: Requires active subscription for anonymous mode
    """
    users_collection = get_users_collection()
    
    # Check if adult user can enable anonymous mode
    if request.enabled and current_user.age_group == "adult":
        from ....models.users import SubscriptionStatus, PlanType
        if current_user.subscription_status == SubscriptionStatus.EXPIRED and current_user.subscription_plan == PlanType.FREE and not current_user.trial_active:
            # Adult users need subscription or active trial for anonymous mode
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anonymous mode requires an active subscription. Please upgrade to the Anonymous plan."
            )
    
    # Update anonymous status
    result = await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$set": {
                "is_anonymous": request.enabled,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    status_text = "enabled" if request.enabled else "disabled"
    return {"message": f"Anonymous mode {status_text} successfully"}

@router.get("/can-send-message",
    response_model=Dict[str, bool],
    summary="Check if user can send message",
    description="Check if user has remaining message allowance",
    responses={
        200: {"description": "Message allowance status returned"},
        401: {"description": "Authentication required"}
    }
)
async def can_send_message(current_user: User = Depends(get_current_active_user)):
    """
    Check if user can send a message based on their plan and usage.
    
    - Teen users: Always can send (unlimited)
    - Adult users: Based on subscription and message count
    """
    # Teen users always can send
    if current_user.age_group == "teen":
        return {"can_send": True}
    
    # Adult users - check limits
    if current_user.max_messages == -1:  # Unlimited (paid subscription)
        return {"can_send": True}
    
    # Check if under limit
    can_send = current_user.message_count < current_user.max_messages
    
    return {"can_send": can_send}

@router.post("/increment-message-count",
    response_model=Dict[str, int],
    summary="Increment message count",
    description="Increment user message count and return new count",
    responses={
        200: {"description": "Message count incremented successfully"},
        401: {"description": "Authentication required"}
    }
)
async def increment_message_count(current_user: User = Depends(get_current_active_user)):
    """
    Increment the user's message count in the database.
    Only increments if the user has remaining messages or unlimited messages.
    
    Returns the updated message count.
    """
    users_collection = get_users_collection()
    
    # Teen users and unlimited plans don't need to increment
    if current_user.age_group == "teen" or current_user.max_messages == -1:
        return {"message_count": current_user.message_count}
    
    # Only increment if under limit
    if current_user.message_count < current_user.max_messages:
        result = await users_collection.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$inc": {"message_count": 1}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=400, 
                detail="Failed to update message count"
            )
        
        return {"message_count": current_user.message_count + 1}
    
    return {"message_count": current_user.message_count}

@router.post("/activate-trial",
    response_model=MessageResponse,
    summary="Activate trial subscription",
    description="Activate trial subscription for adult users",
    responses={
        200: {"description": "Trial activated successfully"},
        400: {"description": "Trial not available or already used"},
        401: {"description": "Authentication required"}
    }
)
async def activate_trial(current_user: User = Depends(get_current_active_user)):
    """
    Activate trial subscription for adult users.
    
    This endpoint is used when users want to start their trial period.
    Teen users don't need trials as they have unlimited access.
    """
    users_collection = get_users_collection()
    
    # Teen users don't need trials
    if current_user.age_group == "teen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teen users have unlimited access and don't need trials"
        )
    
    # Check if trial already used
    if current_user.used_trial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trial has already been used"
        )
    
    # Check if trial is already active
    if current_user.trial_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trial is already active"
        )
    
    # Activate trial - this would typically be handled by Stripe webhook
    # For now, we'll just mark it as available for activation
    result = await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$set": {
                "used_trial": True,  # Mark as used so they can't activate again
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "Trial activation initiated. You will be redirected to complete the setup."}

@router.post("/update-trial-status",
    response_model=MessageResponse,
    summary="Update trial status (Internal)",
    description="Update user trial status - typically called by Stripe webhooks",
    responses={
        200: {"description": "Trial status updated successfully"},
        404: {"description": "User not found"},
        401: {"description": "Authentication required"}
    }
)
async def update_trial_status(
    user_id: str,
    trial_active: bool,
    trial_days: int = 0,
    subscription_status: str = SubscriptionStatus.ACTIVE.value,
    max_messages: int = 0,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update user trial status - typically called by Stripe webhooks or internal processes.
    
    This endpoint updates the trial_active and trial_days fields based on Stripe subscription status.
    """
    users_collection = get_users_collection()
    
    # Only allow admins or the user themselves to update trial status
    if current_user.user_type not in [UserType.ADMIN, UserType.SUPER_ADMIN] and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "trial_active": trial_active,
                "trial_days": trial_days,
                "subscription_status": subscription_status,
                "max_messages": max_messages,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "Trial status updated successfully"}

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ):
        json_schema = handler(core_schema)
        json_schema["type"] = "string"
        return json_schema