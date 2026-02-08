"""
Authentication middleware for handling credential expiration.
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class CredentialExpirationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle credential expiration gracefully.
    
    This middleware intercepts 401 errors and adds helpful information
    for the frontend to handle re-authentication flows.
    """
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
            
        except HTTPException as exc:
            # Check if this is a credential expiration error
            if exc.status_code == 401:
                logger.warning(f"Authentication error on {request.url.path}: {exc.detail}")
                
                # Return structured error response
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "authentication_required",
                        "message": exc.detail,
                        "action": "re_authenticate",
                        "detail": "Your session has expired. Please submit new Kion credentials."
                    },
                    headers=exc.headers or {}
                )
            
            # Re-raise other HTTP exceptions
            raise
        
        except Exception as e:
            logger.error(f"Unexpected error in auth middleware: {e}")
            raise


def check_credential_expiration_soon(time_remaining_seconds: int) -> dict:
    """
    Check if credentials are expiring soon and return warning info.
    
    Args:
        time_remaining_seconds: Seconds until expiration
        
    Returns:
        Dictionary with warning info if expiring soon, empty dict otherwise
    """
    if time_remaining_seconds <= 0:
        return {
            "warning": "expired",
            "message": "Credentials have expired. Please re-authenticate.",
            "action_required": True
        }
    elif time_remaining_seconds < 600:  # Less than 10 minutes
        return {
            "warning": "expiring_soon",
            "message": f"Credentials will expire in {time_remaining_seconds // 60} minutes. Consider re-authenticating.",
            "action_required": False,
            "time_remaining_seconds": time_remaining_seconds
        }
    
    return {}
