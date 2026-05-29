"""
Account Status Management Service

This service handles user account status transitions, validation, and audit logging
according to the user approval system requirements.
"""

from typing import Optional
from datetime import datetime
from fastapi import HTTPException, status
from bson import ObjectId

from ..models.users import AccountStatus, User
from ..database import get_users_collection
from ..auth.utils import get_user_by_id


class AccountStatusManager:
    """Service for managing user account status transitions and validation"""
    
    # Define allowed status transitions based on requirements 4.2, 4.3, 4.4, 4.5
    # Updated: allow re-activation (transition to ACTIVATED) from any prior status, including previously "final" states
    ALLOWED_TRANSITIONS = {
        AccountStatus.REQUESTED: [AccountStatus.ACTIVATED, AccountStatus.REJECTED, AccountStatus.REFUSED],
        AccountStatus.ACTIVATED: [AccountStatus.DEACTIVATED],
        AccountStatus.DEACTIVATED: [AccountStatus.ACTIVATED],
        AccountStatus.REJECTED: [AccountStatus.ACTIVATED],  # Reactivation now permitted
        AccountStatus.REFUSED: [AccountStatus.ACTIVATED]    # Reactivation now permitted
    }
    
    @staticmethod
    def can_transition(from_status: AccountStatus, to_status: AccountStatus) -> bool:
        """
        Check if a status transition is allowed based on business rules.
        
        Args:
            from_status: Current account status
            to_status: Desired new account status
            
        Returns:
            bool: True if transition is allowed, False otherwise
        """
        return to_status in AccountStatusManager.ALLOWED_TRANSITIONS.get(from_status, [])
    
    @staticmethod
    async def update_user_status(
        user_id: str, 
        new_status: AccountStatus, 
        admin_id: str, 
        reason: Optional[str] = None
    ) -> bool:
        """
        Update user account status with validation and audit logging.
        
        Args:
            user_id: ID of the user whose status to update
            new_status: New account status to set
            admin_id: ID of the admin making the change
            reason: Optional reason for the status change
            
        Returns:
            bool: True if update was successful, False otherwise
            
        Raises:
            HTTPException: If user not found or transition is not allowed
        """
        users_collection = get_users_collection()
        
        # Get current user
        user = await get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate transition according to requirements 4.2, 4.3, 4.4, 4.5
        if not AccountStatusManager.can_transition(user.account_status, new_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from {user.account_status.value} to {new_status.value}"
            )
        
        # Prepare update data with audit trail
        update_data = {
            "account_status": new_status.value,
            "status_changed_at": datetime.utcnow(),
            "status_changed_by": admin_id,
            "updated_at": datetime.utcnow()
        }
        
        # Update is_active field based on status (requirement 1.5, 1.6)
        if new_status == AccountStatus.ACTIVATED:
            update_data["is_active"] = True
        elif new_status in [AccountStatus.DEACTIVATED, AccountStatus.REJECTED, AccountStatus.REFUSED]:
            update_data["is_active"] = False
        else:  # REQUESTED
            update_data["is_active"] = False
        
        # Perform the update
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    @staticmethod
    async def get_pending_requests_count() -> int:
        """
        Get count of users with requested status for admin dashboard.
        
        Returns:
            int: Number of users with 'requested' status
        """
        users_collection = get_users_collection()
        count = await users_collection.count_documents({
            "account_status": AccountStatus.REQUESTED.value
        })
        return count
    
    @staticmethod
    def get_status_message(account_status: AccountStatus) -> str:
        """
        Get user-friendly message for account status based on requirements 5.1, 5.2, 5.3, 5.4.
        
        Args:
            account_status: The account status to get message for
            
        Returns:
            str: User-friendly status message
        """
        messages = {
            AccountStatus.REQUESTED: "Your account is pending approval. Please wait for an admin to activate your account.",
            AccountStatus.REJECTED: "Your account has been rejected. Please contact support if you believe this is an error.",
            AccountStatus.REFUSED: "Access to your account has been refused.",
            AccountStatus.DEACTIVATED: "Your account has been deactivated. Please contact support.",
            AccountStatus.ACTIVATED: "Your account is active."
        }
        return messages.get(account_status, "Unknown account status.")
    
    @staticmethod
    def validate_status_transition_rules(from_status: AccountStatus, to_status: AccountStatus) -> None:
        """
        Validate status transition rules and raise appropriate exceptions.
        
        Args:
            from_status: Current account status
            to_status: Desired new account status
            
        Raises:
            HTTPException: If transition is not allowed with detailed error message
        """
        if not AccountStatusManager.can_transition(from_status, to_status):
            # Provide specific error messages based on transition rules.
            # Rejected / refused are no longer permanently final if transitioning to activated is requested.
            allowed_statuses = AccountStatusManager.ALLOWED_TRANSITIONS.get(from_status, [])
            allowed_names = [status.value for status in allowed_statuses]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from {from_status.value} to {to_status.value}. "
                       f"Allowed transitions: {', '.join(allowed_names) if allowed_names else 'none'}"
            )
    
    @staticmethod
    async def get_users_by_status(account_status: AccountStatus) -> list:
        """
        Get all users with a specific account status.
        
        Args:
            account_status: The status to filter by
            
        Returns:
            list: List of users with the specified status
        """
        users_collection = get_users_collection()
        users_cursor = users_collection.find(
            {"account_status": account_status.value},
            {"hashed_password": 0, "refresh_token": 0}  # Exclude sensitive fields
        )
        
        users = []
        async for user_doc in users_cursor:
            user_doc["_id"] = str(user_doc["_id"])
            users.append(user_doc)
        
        return users
    
    @staticmethod
    async def get_status_statistics() -> dict:
        """
        Get statistics about user account statuses for admin dashboard.
        
        Returns:
            dict: Dictionary with counts for each status
        """
        users_collection = get_users_collection()
        
        # Use aggregation to get counts for all statuses
        pipeline = [
            {
                "$group": {
                    "_id": "$account_status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        result = {}
        async for doc in users_collection.aggregate(pipeline):
            status = doc["_id"] or AccountStatus.REQUESTED.value  # Handle null values
            result[status] = doc["count"]
        
        # Ensure all statuses are represented
        for status in AccountStatus:
            if status.value not in result:
                result[status.value] = 0
        
        return result