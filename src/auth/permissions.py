from fastapi import HTTPException, status
from ..models.users import User, UserType

class PermissionChecker:
    """Class to handle role-based permissions"""
    
    @staticmethod
    def check_admin_permission(user: User):
        """Check if user has admin permissions"""
        if user.user_type not in [UserType.ADMIN, UserType.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin permissions required"
            )
    
    @staticmethod
    def check_moderator_permission(user: User):
        """Check if user has moderator or higher permissions"""
        if user.user_type not in [UserType.MODERATOR, UserType.ADMIN, UserType.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Moderator permissions or higher required"
            )
    
    @staticmethod
    def check_super_admin_permission(user: User):
        """Check if user has super admin permissions"""
        if user.user_type != UserType.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin permissions required"
            )
    
    @staticmethod
    def can_manage_user(current_user: User, target_user: User) -> bool:
        """Check if current user can manage target user"""
        # Super admin can manage anyone
        if current_user.user_type == UserType.SUPER_ADMIN:
            return True
        
        # Admin can manage moderators and customers
        if current_user.user_type == UserType.ADMIN:
            return target_user.user_type in [UserType.MODERATOR, UserType.CUSTOMER]
        
        # Moderator can manage customers
        if current_user.user_type == UserType.MODERATOR:
            return target_user.user_type == UserType.CUSTOMER
        
        # Customers can only manage themselves
        return current_user.id == target_user.id
    
    @staticmethod
    def get_user_permissions(user_type: UserType) -> dict:
        """Get permissions for a user type"""
        permissions = {
            UserType.CUSTOMER: {
                "can_create_ideas": True,
                "can_view_own_data": True,
                "can_subscribe": True,
                "can_export_pdf": False,  # Only with subscription
                "can_view_analytics": False,
                "can_manage_users": False,
                "can_moderate_content": False,
                "can_access_admin_panel": False,
            },
            UserType.MODERATOR: {
                "can_create_ideas": True,
                "can_view_own_data": True,
                "can_subscribe": True,
                "can_export_pdf": True,
                "can_view_analytics": True,
                "can_manage_users": False,
                "can_moderate_content": True,
                "can_access_admin_panel": True,
            },
            UserType.ADMIN: {
                "can_create_ideas": True,
                "can_view_own_data": True,
                "can_subscribe": True,
                "can_export_pdf": True,
                "can_view_analytics": True,
                "can_manage_users": True,
                "can_moderate_content": True,
                "can_access_admin_panel": True,
            },
            UserType.SUPER_ADMIN: {
                "can_create_ideas": True,
                "can_view_own_data": True,
                "can_subscribe": True,
                "can_export_pdf": True,
                "can_view_analytics": True,
                "can_manage_users": True,
                "can_moderate_content": True,
                "can_access_admin_panel": True,
                "can_manage_system": True,
            }
        }
        return permissions.get(user_type, permissions[UserType.CUSTOMER])
