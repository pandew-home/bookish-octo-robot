"""
EKS Authentication utilities for generating bearer tokens and validating credentials.
"""
import base64
import boto3
from botocore.signers import RequestSigner
from datetime import datetime
from typing import Tuple, Optional
import logging

from credential_store import StoredCredentials

logger = logging.getLogger(__name__)

# Token expiration time (60 seconds as per AWS EKS spec)
TOKEN_EXPIRATION_SECONDS = 60


def get_eks_bearer_token(creds: StoredCredentials, cluster_name: str) -> str:
    """
    Generate an EKS bearer token from STS credentials.
    
    This implements the equivalent of `aws eks get-token` command by creating
    a presigned GetCallerIdentity URL and encoding it as a Kubernetes token.
    
    Args:
        creds: AWS credentials
        cluster_name: Name of the EKS cluster
        
    Returns:
        Bearer token in format: k8s-aws-v1.{base64_encoded_signed_url}
        
    Raises:
        Exception: If token generation fails
    """
    try:
        # Create STS client with provided credentials
        session = boto3.Session(
            aws_access_key_id=creds.access_key,
            aws_secret_access_key=creds.secret_key,
            aws_session_token=creds.session_token,
            region_name=creds.region
        )
        
        sts_client = session.client('sts')
        
        # Create a request signer
        signer = RequestSigner(
            service_name='sts',
            region_name=creds.region,
            signing_name='sts',
            signature_version='v4',
            credentials=session.get_credentials(),
            event_emitter=sts_client.meta.events
        )
        
        # Prepare the GetCallerIdentity request
        request_params = {
            'method': 'GET',
            'url': f'https://sts.{creds.region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
            'body': {},
            'headers': {
                'x-k8s-aws-id': cluster_name
            },
            'context': {}
        }
        
        # Sign the request
        signed_url = signer.generate_presigned_url(
            request_params,
            region_name=creds.region,
            expires_in=TOKEN_EXPIRATION_SECONDS,
            operation_name=''
        )
        
        # Encode the signed URL as base64
        token_bytes = signed_url.encode('utf-8')
        token_b64 = base64.urlsafe_b64encode(token_bytes).decode('utf-8').rstrip('=')
        
        # Format as k8s-aws-v1 token
        bearer_token = f'k8s-aws-v1.{token_b64}'
        
        logger.info(f"Generated EKS bearer token for cluster {cluster_name}")
        return bearer_token
        
    except Exception as e:
        logger.error(f"Failed to generate EKS bearer token: {e}")
        raise


def validate_credentials(
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str
) -> Tuple[bool, Optional[StoredCredentials], Optional[str]]:
    """
    Validate AWS credentials via STS GetCallerIdentity.
    
    Args:
        access_key: AWS access key ID
        secret_key: AWS secret access key
        session_token: AWS session token
        region: AWS region
        
    Returns:
        Tuple of (success, credentials, error_message)
        - success: True if credentials are valid
        - credentials: StoredCredentials object if valid, None otherwise
        - error_message: Error description if invalid, None otherwise
    """
    try:
        # Create STS client
        sts_client = boto3.client(
            'sts',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            region_name=region
        )
        
        # Call GetCallerIdentity to validate credentials
        response = sts_client.get_caller_identity()
        
        # Extract user information
        user_arn = response['Arn']
        account_id = response['Account']
        
        # Create StoredCredentials object
        now = datetime.now()
        creds = StoredCredentials(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=region,
            user_arn=user_arn,
            account_id=account_id,
            expires_at=now,  # Will be set by CredentialStore
            created_at=now
        )
        
        logger.info(f"Validated credentials for user {user_arn}")
        return True, creds, None
        
    except sts_client.exceptions.InvalidClientTokenId:
        error_msg = "Invalid access key ID. Please check your Kion credentials."
        logger.warning(f"Credential validation failed: {error_msg}")
        return False, None, error_msg
        
    except sts_client.exceptions.SignatureDoesNotMatch:
        error_msg = "Invalid secret access key. Please check your Kion credentials."
        logger.warning(f"Credential validation failed: {error_msg}")
        return False, None, error_msg
        
    except Exception as e:
        error_msg = f"Failed to validate credentials: {str(e)}"
        logger.error(f"Credential validation error: {e}")
        return False, None, error_msg


def get_credential_expiration_info(creds: StoredCredentials) -> dict:
    """
    Get information about credential expiration.
    
    Args:
        creds: Stored credentials
        
    Returns:
        Dictionary with expiration info
    """
    now = datetime.now()
    time_remaining = (creds.expires_at - now).total_seconds()
    
    if time_remaining <= 0:
        status = "expired"
    elif time_remaining < 600:  # Less than 10 minutes
        status = "expiring_soon"
    else:
        status = "active"
    
    return {
        "status": status,
        "expires_at": creds.expires_at.isoformat(),
        "time_remaining_seconds": max(0, int(time_remaining)),
        "user_arn": creds.user_arn,
        "account_id": creds.account_id,
        "region": creds.region
    }
