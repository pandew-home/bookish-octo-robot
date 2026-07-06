"""
API endpoints for credential management (AWS + Kubeconfig).
"""
import os
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import uuid
import logging
from datetime import datetime, timedelta

from credential_store import CredentialStore, StoredCredentials
from eks_auth import validate_credentials, get_credential_expiration_info
from local_k8s_auth import (
    validate_kubeconfig, 
    discover_local_clusters,
    validate_kubeconfig_content,
    parse_kubeconfig_content,
    get_k8s_client_from_content
)
from middleware.auth_middleware import check_credential_expiration_soon
from utils.error_handler import handle_aws_error, handle_generic_error
from cluster_manager import discover_clusters, get_k8s_clients, cleanup_k8s_clients

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

# Global credential store instance
credential_store = CredentialStore(max_capacity=1000, ttl_seconds=3600)


def get_target_eks_cluster_name() -> Optional[str]:
    """Return configured in-cluster target EKS cluster name, if any."""
    return (
        os.getenv("IN_CLUSTER_EKS_CLUSTER_NAME")
        or os.getenv("EKS_CLUSTER_NAME")
        or None
    )


async def _verify_aws_access_to_target_cluster(creds: StoredCredentials) -> None:
    """Validate that user credentials can access the configured chatbot cluster."""
    target_cluster_name = get_target_eks_cluster_name()
    if not target_cluster_name:
        return

    clusters = await discover_clusters(creds)
    target_cluster = next((c for c in clusters if c.get("name") == target_cluster_name), None)
    if target_cluster is None:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Credentials do not have access to target cluster '{target_cluster_name}'. "
                "Use credentials with access to this chatbot cluster."
            ),
        )

    clients = get_k8s_clients(creds, target_cluster)
    try:
        clients["core_v1"].list_namespace(limit=1)
    except Exception as e:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Credentials were validated in AWS but cannot access cluster '{target_cluster_name}'. "
                f"Cluster access check failed: {e}"
            ),
        )
    finally:
        cleanup_k8s_clients(clients)


class KionCredentials(BaseModel):
    """Request model for Kion AWS credentials."""
    access_key_id: str = Field(..., min_length=16, max_length=128, description="AWS access key ID")
    secret_access_key: str = Field(..., min_length=16, description="AWS secret access key")
    session_token: str = Field(..., min_length=16, description="AWS session token")
    region: str = Field(..., description="AWS region")


class KubeconfigCredentials(BaseModel):
    """Request model for kubeconfig credentials (legacy - file path based)."""
    kubeconfig_path: str = Field(..., description="Path to kubeconfig file")


class KubeconfigContentRequest(BaseModel):
    """Request model for kubeconfig content parsing."""
    content: str = Field(..., description="Raw YAML content of kubeconfig")


class KubeconfigAuthRequest(BaseModel):
    """Request model for kubeconfig authentication with context selection."""
    content: str = Field(..., description="Raw YAML content of kubeconfig")
    context: str = Field(..., description="Selected context name")


class KubeconfigContextInfo(BaseModel):
    """Model for a single kubeconfig context."""
    name: str
    cluster: str


class KubeconfigParseResponse(BaseModel):
    """Response model for kubeconfig parsing."""
    contexts: List[KubeconfigContextInfo]
    currentContext: Optional[str] = None  # camelCase for frontend compatibility


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
    auth_mode: Optional[str] = None  # "aws" or "kubeconfig"
    expires_at: Optional[str] = None
    time_remaining_seconds: Optional[int] = None
    user_arn: Optional[str] = None
    account_id: Optional[str] = None
    region: Optional[str] = None
    kubeconfig_contexts: Optional[Dict[str, str]] = None
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
    2. Stores them in the credential store with TTL (auth_mode="aws")
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
        
        if not success or creds is None:
            logger.warning(f"Credential validation failed: {error}")
            raise HTTPException(status_code=401, detail=error)
        
        # Set auth mode
        creds.auth_mode = "aws"

        # Ensure credentials work for the chatbot's configured in-cluster target.
        await _verify_aws_access_to_target_cluster(creds)
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store credentials
        credential_store.store(session_id, creds)
        
        logger.info(f"Stored AWS credentials for user {creds.user_arn} with session {session_id[:8]}...")
        
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


@router.post("/kubeconfig", response_model=CredentialResponse)
async def submit_kubeconfig_credentials(credentials: KubeconfigCredentials):
    """
    Submit and validate kubeconfig credentials.
    
    This endpoint:
    1. Validates the kubeconfig file
    2. Discovers available clusters/contexts
    3. Stores them in the credential store with TTL (auth_mode="kubeconfig")
    4. Returns a session ID for subsequent requests
    
    Args:
        credentials: Kubeconfig credentials
        
    Returns:
        CredentialResponse with session ID
        
    Raises:
        HTTPException: If kubeconfig is invalid
    """
    try:
        logger.info(f"=== Kubeconfig authentication request ===")
        logger.info(f"Received kubeconfig path: {credentials.kubeconfig_path}")
        
        # Validate kubeconfig
        logger.info("Calling validate_kubeconfig...")
        is_valid = validate_kubeconfig(credentials.kubeconfig_path)
        logger.info(f"validate_kubeconfig returned: {is_valid}")
        
        if not is_valid:
            logger.warning(f"Kubeconfig validation failed for: {credentials.kubeconfig_path}")
            raise HTTPException(status_code=400, detail="Invalid kubeconfig file")
        
        # Discover clusters from kubeconfig
        kubeconfig_contexts = discover_local_clusters(credentials.kubeconfig_path)
        
        if not kubeconfig_contexts:
            raise HTTPException(status_code=400, detail="No contexts found in kubeconfig")
        
        # Create stored credentials
        now = datetime.now()
        creds = StoredCredentials(
            auth_mode="kubeconfig",
            kubeconfig_path=credentials.kubeconfig_path,
            kubeconfig_contexts=kubeconfig_contexts,
            created_at=now,
            expires_at=now + timedelta(hours=1)  # 1 hour TTL
        )
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store credentials
        credential_store.store(session_id, creds)
        
        logger.info(f"Stored kubeconfig credentials with {len(kubeconfig_contexts)} contexts, session {session_id[:8]}...")
        
        return CredentialResponse(
            success=True,
            session_id=session_id,
            message=f"Kubeconfig validated successfully. Found {len(kubeconfig_contexts)} contexts.",
            user_arn=None,
            account_id=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting kubeconfig: {e}")
        raise handle_generic_error(
            e,
            "validating your kubeconfig",
            "Unable to validate kubeconfig. Please check the file path and permissions."
        )


@router.post("/kubeconfig/parse", response_model=KubeconfigParseResponse)
async def parse_kubeconfig(request: KubeconfigContentRequest):
    """
    Parse kubeconfig content and return available contexts.
    
    This endpoint allows the frontend to upload kubeconfig content
    (via file upload or paste) and get a list of available contexts
    for the user to select from.
    
    Args:
        request: Kubeconfig content request with raw YAML
        
    Returns:
        KubeconfigParseResponse with list of contexts
        
    Raises:
        HTTPException: If kubeconfig content is invalid
    """
    try:
        logger.info("=== Parsing kubeconfig content ===")
        logger.info(f"Content length: {len(request.content)} characters")
        
        # Parse kubeconfig content
        parsed_data, error = parse_kubeconfig_content(request.content)
        
        if error:
            logger.warning(f"Kubeconfig parse error: {error}")
            raise HTTPException(status_code=400, detail=error)
        
        if not parsed_data or not parsed_data.get('contexts'):
            raise HTTPException(status_code=400, detail="No contexts found in kubeconfig")
        
        # Build response
        contexts = [
            KubeconfigContextInfo(
                name=ctx['name'],
                cluster=ctx['cluster']
            )
            for ctx in parsed_data['contexts']
        ]
        
        logger.info(f"Found {len(contexts)} contexts, current={parsed_data.get('current_context')}")
        
        return KubeconfigParseResponse(
            contexts=contexts,
            currentContext=parsed_data.get('current_context')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing kubeconfig: {e}")
        raise handle_generic_error(
            e,
            "parsing kubeconfig",
            "Unable to parse kubeconfig. Please check the content format."
        )


@router.post("/kubeconfig/auth", response_model=CredentialResponse)
async def auth_kubeconfig_content(request: KubeconfigAuthRequest):
    """
    Authenticate with kubeconfig content and selected context.
    
    This endpoint accepts the kubeconfig content (streamed from browser)
    and the user-selected context, validates them, and creates a session.
    
    Args:
        request: Kubeconfig auth request with content and selected context
        
    Returns:
        CredentialResponse with session ID
        
    Raises:
        HTTPException: If kubeconfig or context is invalid
    """
    try:
        logger.info("=== Kubeconfig content authentication ===")
        logger.info(f"Content length: {len(request.content)} characters")
        logger.info(f"Selected context: {request.context}")
        
        # Validate kubeconfig content
        is_valid, error = validate_kubeconfig_content(request.content)
        if not is_valid:
            logger.warning(f"Kubeconfig validation failed: {error}")
            raise HTTPException(status_code=400, detail=error)
        
        # Parse to get contexts
        parsed_data, error = parse_kubeconfig_content(request.content)
        if error or not parsed_data:
            raise HTTPException(status_code=400, detail=error or "Failed to parse kubeconfig")
        
        # Verify selected context exists
        context_names = [ctx['name'] for ctx in parsed_data.get('contexts', [])]
        if request.context not in context_names:
            raise HTTPException(
                status_code=400, 
                detail=f"Context '{request.context}' not found. Available: {context_names}"
            )
        
        # Build contexts dict for storage
        kubeconfig_contexts = {
            ctx['name']: ctx['cluster'] 
            for ctx in parsed_data.get('contexts', [])
        }
        
        # Create stored credentials
        now = datetime.now()
        creds = StoredCredentials(
            auth_mode="kubeconfig",
            kubeconfig_content=request.content,  # Store content for later use
            kubeconfig_contexts=kubeconfig_contexts,
            selected_context=request.context,
            created_at=now,
            expires_at=now + timedelta(hours=1)  # 1 hour TTL
        )
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store credentials
        credential_store.store(session_id, creds)
        
        logger.info(f"Stored kubeconfig credentials with context '{request.context}', session {session_id[:8]}...")
        
        return CredentialResponse(
            success=True,
            session_id=session_id,
            message=f"Authenticated with context '{request.context}' successfully.",
            user_arn=None,
            account_id=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error authenticating kubeconfig: {e}")
        raise handle_generic_error(
            e,
            "authenticating with kubeconfig",
            "Unable to authenticate with kubeconfig. Please check the content and selected context."
        )


@router.get("/status", response_model=CredentialStatusResponse)
async def get_credential_status(session_id: str = Depends(get_session_id)):
    """
    Get status of stored credentials (AWS or kubeconfig).
    
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
                auth_mode=None,
                expires_at=None,
                time_remaining_seconds=None
            )
        
        # Get expiration info
        info = get_credential_expiration_info(creds)
        
        # Check for expiration warnings
        warning = check_credential_expiration_soon(info['time_remaining_seconds'])
        
        # Build response based on auth mode
        response = CredentialStatusResponse(
            status=info['status'],
            auth_mode=creds.auth_mode,
            expires_at=info['expires_at'],
            time_remaining_seconds=info['time_remaining_seconds'],
            warning=warning if warning else None
        )
        
        if creds.auth_mode == "aws":
            response.user_arn = info['user_arn']
            response.account_id = info['account_id']
            response.region = info['region']
        elif creds.auth_mode == "kubeconfig":
            response.kubeconfig_contexts = creds.kubeconfig_contexts
            
        return response
        
    except Exception as e:
        logger.error(f"Error getting credential status: {e}")
        raise handle_generic_error(
            e,
            "checking credential status",
            "Unable to check credential status. Please try again."
        )


@router.delete("/")
async def delete_credentials(session_id: str = Depends(get_session_id)):
    """
    Delete stored credentials (AWS or kubeconfig).
    
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
