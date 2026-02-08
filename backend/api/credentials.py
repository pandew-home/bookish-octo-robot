"""
API endpoints for AWS credential management.
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional
import uuid
import logging

from credential_store import CredentialStore, StoredCredentials
from eks_auth import validate_credentials, get_credential_expiration_info
from middleware.auth_middleware import check_credential_expiration_soon
from utils.error_handler import handle_aws_error, handle_generic_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

# Global credential store instance
credential_store = CredentialStore(max_capacity=1000, ttl_seconds=3600)


class KionCredentials(BaseModel):
    """Request model for Kion AWS credentials."""
    access_key_id: str = Field(..., min_length=16, max_length=128, description="AWS access key ID")
    secret_access_key: str = Field(..., min_length=16, description="AWS secret access key")
    session_token: str = Field(..., min_length=16, description="AWS session token")
    region: str = Field(..., description="AWS region")


class CredentialResponse(BaseModel):
    """Response model for credential submission."""
    success: bool
    session_id: Optional[str] = None
    message: str
    user_arn: Optional[str] = None
    account_id: Optional[str] = None


class CredentialStatusResponse(BaseModel):
    """Response model for credential status."""
    status: str  # "no_credentials", "active", "expiring_soon", "expired"
    expires_at: Optional[str] = None
    time_remaining_seconds: Optional[int] = None
    user_arn: Optional[str] = None
    account_id: Optional[str] = None
    region: Optional[str] = None
    warning: Optional[dict] = None  # Warning info if expiring soon


def get_session_id(x_session_id: Optional[str] = Header(None)) -> str:
    """
    Extract session ID from header.
    
    Args:
        x_session_id: Session ID from X-Session-Id header
        
    Returns:
        Session ID
        
    Raises:
        HTTPException: If session ID is missing
    """
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    return x_session_id


@router.post("/aws", response_model=CredentialResponse)
async def submit_aws_credentials(credentials: KionCredentials):
    """
    Submit and validate Kion AWS credentials.
    
    This endpoint:
    1. Validates credentials via STS GetCallerIdentity
    2. Stores them in the credential store with TTL
    3. Returns a session ID for subsequent requests
    
    Args:
        credentials: Kion AWS credentials
        
    Returns:
        CredentialResponse with session ID and user info
        
    Raises:
        HTTPException: If credentials are invalid
    """
    try:
        logger.info(f"Validating AWS credentials for region {credentials.region}")
        
        # Validate credentials
        success, creds, error = validate_credentials(
            access_key=credentials.access_key_id,
            secret_key=credentials.secret_access_key,
            session_token=credentials.session_token,
            region=credentials.region
        )
        
        if not success:
            logger.warning(f"Credential validation failed: {error}")
            raise HTTPException(status_code=401, detail=error)
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store credentials
        credential_store.store(session_id, creds)
        
        logger.info(f"Stored credentials for user {creds.user_arn} with session {session_id[:8]}...")
        
        return CredentialResponse(
            success=True,
            session_id=session_id,
            message="Credentials validated and stored successfully",
            user_arn=creds.user_arn,
            account_id=creds.account_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting credentials: {e}")
        raise handle_generic_error(
            e,
            "validating your credentials",
            "Unable to validate credentials. Please check your Kion credentials and try again."
        )


@router.get("/aws/status", response_model=CredentialStatusResponse)
async def get_credential_status(session_id: str = Depends(get_session_id)):
    """
    Get status of stored AWS credentials.
    
    Args:
        session_id: Session ID from header
        
    Returns:
        CredentialStatusResponse with expiration info
    """
    try:
        # Retrieve credentials
        creds = credential_store.get(session_id)
        
        if creds is None:
            return CredentialStatusResponse(
                status="no_credentials",
                expires_at=None,
                time_remaining_seconds=None
            )
        
        # Get expiration info
        info = get_credential_expiration_info(creds)
        
        # Check for expiration warnings
        warning = check_credential_expiration_soon(info['time_remaining_seconds'])
        
        return CredentialStatusResponse(
            status=info['status'],
            expires_at=info['expires_at'],
            time_remaining_seconds=info['time_remaining_seconds'],
            user_arn=info['user_arn'],
            account_id=info['account_id'],
            region=info['region'],
            warning=warning if warning else None
        )
        
    except Exception as e:
        logger.error(f"Error getting credential status: {e}")
        raise handle_generic_error(
            e,
            "checking credential status",
            "Unable to check credential status. Please try again."
        )


@router.delete("/aws")
async def delete_credentials(session_id: str = Depends(get_session_id)):
    """
    Delete stored AWS credentials.
    
    Args:
        session_id: Session ID from header
        
    Returns:
        Success message
    """
    try:
        removed = credential_store.remove(session_id)
        
        if removed:
            logger.info(f"Removed credentials for session {session_id[:8]}...")
            return {"success": True, "message": "Credentials removed successfully"}
        else:
            return {"success": False, "message": "No credentials found for session"}
            
    except Exception as e:
        logger.error(f"Error deleting credentials: {e}")
        raise handle_generic_error(
            e,
            "deleting credentials",
            "Unable to delete credentials. Please try again."
        )


def get_credentials_for_session(session_id: str) -> StoredCredentials:
    """
    Helper function to get credentials for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        StoredCredentials
        
    Raises:
        HTTPException: If credentials not found or expired
            - 401 with "credentials_expired" detail if expired
            - 401 with "credentials_missing" detail if not found
    """
    creds = credential_store.get(session_id)
    
    if creds is None:
        # Check if credentials existed but expired vs never existed
        # This helps frontend distinguish between "need to re-auth" vs "never authenticated"
        raise HTTPException(
            status_code=401,
            detail="Credentials expired or not found. Please re-authenticate.",
            headers={"X-Auth-Status": "credentials_expired"}
        )
    
    return creds
