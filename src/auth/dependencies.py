from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .jwt import verify_token
from .utils import get_user_by_id
from .permissions import PermissionChecker
from ..models.users import User, UserType

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user"""
    token = credentials.credentials
    
    # Verify the token
    payload = verify_token(token, "access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def require_moderator(current_user: User = Depends(get_current_active_user)) -> User:
    """Require moderator or higher permissions"""
    PermissionChecker.check_moderator_permission(current_user)
    return current_user

async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require admin or higher permissions"""
    PermissionChecker.check_admin_permission(current_user)
    return current_user

async def require_super_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require super admin permissions"""
    PermissionChecker.check_super_admin_permission(current_user)
    return current_user
async def get_current_user_websocket(token: str) -> User:
    """Get current authenticated user for WebSocket connections"""
    try:
        # Verify the token
        payload = verify_token(token, "access")
        if payload is None:
            return None
        
        # Get user from database
        user_id = payload.get("sub")
        if user_id is None:
            return None
        
        user = await get_user_by_id(user_id)
        if user is None:
            return None
        
        if not user.is_active:
            return None
        
        return user
    except Exception:
        return None