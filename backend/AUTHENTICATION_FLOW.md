# Authentication Flow and Error Handling

## Overview

DevOps Chatbot v2 uses Kion temporary AWS credentials for authentication. This document explains the complete authentication flow, credential lifecycle, and error handling.

## Authentication Flow

### 1. Initial Authentication

```
User → Frontend → POST /api/credentials/aws
                   ↓
              Validate via STS GetCallerIdentity
                   ↓
              Store in CredentialStore (TTL: 3600s)
                   ↓
              Return session_id
                   ↓
              Frontend stores session_id in localStorage/sessionStorage
```

### 2. Subsequent Requests

All API requests include the session ID in the `X-Session-Id` header:

```
Frontend → API Request with X-Session-Id header
           ↓
       get_credentials_for_session()
           ↓
       Check CredentialStore
           ↓
   ┌───────┴───────┐
   │               │
Valid           Expired/Missing
   │               │
Continue        Return 401
   │               │
Execute         Frontend detects 401
Request         and prompts re-auth
```

## Credential Lifecycle

### States

1. **Active** (>10 minutes remaining)
   - Status: `active`
   - Action: None required
   - Frontend: Normal operation

2. **Expiring Soon** (<10 minutes remaining)
   - Status: `expiring_soon`
   - Action: Show warning banner
   - Frontend: Display countdown, suggest re-authentication

3. **Expired** (0 minutes remaining)
   - Status: `expired`
   - Action: Block requests, require re-authentication
   - Frontend: Redirect to login, clear session

### Credential Status Polling

Frontend should poll `GET /api/credentials/aws/status` every 30 seconds:

```typescript
// Example frontend polling
setInterval(async () => {
  const response = await fetch('/api/credentials/aws/status', {
    headers: { 'X-Session-Id': sessionId }
  });
  
  const status = await response.json();
  
  if (status.status === 'expired') {
    // Redirect to login
    redirectToLogin();
  } else if (status.status === 'expiring_soon') {
    // Show warning banner
    showExpirationWarning(status.time_remaining_seconds);
  }
}, 30000);
```

## Error Handling

### 401 Unauthorized Errors

When credentials expire or are missing, the API returns:

```json
{
  "error": "authentication_required",
  "message": "Credentials expired or not found. Please re-authenticate.",
  "action": "re_authenticate",
  "detail": "Your session has expired. Please submit new Kion credentials."
}
```

**Frontend Response:**
1. Clear stored session_id
2. Clear any cached cluster/chat data
3. Redirect to login page
4. Show user-friendly message: "Your session has expired. Please log in again."

### Graceful Degradation

When credentials expire mid-operation:

1. **During Chat Query:**
   - Return 401 immediately
   - Frontend shows: "Session expired. Please re-authenticate to continue."
   - Preserve unsent message in draft

2. **During Cluster Discovery:**
   - Return 401 immediately
   - Frontend shows: "Session expired. Please re-authenticate to view clusters."

3. **During Weather Polling:**
   - Stop polling
   - Show last known state with "Session expired" overlay
   - Don't spam error messages

## CA Certificate Handling

### Why CA Certificates Are Needed

EKS clusters use TLS/SSL to secure the Kubernetes API endpoint. The CA certificate is required to:

1. **Verify Server Identity:** Ensures we're connecting to the legitimate EKS cluster
2. **Prevent MITM Attacks:** Validates the server's SSL certificate chain
3. **Establish Secure Connection:** Required for TLS handshake

### How It Works

```
1. AWS EKS provides CA cert in base64-encoded format
   ↓
2. Backend decodes the base64 data
   ↓
3. Writes decoded cert to temporary file
   ↓
4. Kubernetes client uses file path for SSL verification
   ↓
5. Secure TLS connection established
   ↓
6. Temp file cleaned up when session ends
```

### Security Considerations

- **Temporary Files:** CA certs are written to temp files with restricted permissions
- **Cleanup:** Files are deleted when K8s clients are closed or session ends
- **No Caching:** CA certs are not cached to prevent stale certificates
- **Per-Session:** Each session gets its own temp file to avoid conflicts

### Example Flow

```python
# 1. Get cluster info from EKS
cluster_info = eks.describe_cluster(name='my-cluster')
ca_data_b64 = cluster_info['cluster']['certificateAuthority']['data']

# 2. Decode CA certificate
ca_cert_bytes = base64.b64decode(ca_data_b64)

# 3. Write to temp file
ca_cert_file = tempfile.NamedTemporaryFile(delete=False, suffix='.crt')
ca_cert_file.write(ca_cert_bytes)
ca_cert_path = ca_cert_file.name

# 4. Configure K8s client
config = Configuration()
config.host = cluster_endpoint
config.api_key = {"authorization": f"Bearer {bearer_token}"}
config.ssl_ca_cert = ca_cert_path  # ← CA cert used here
config.verify_ssl = True

# 5. Create API client
api_client = k8s_client.ApiClient(config)

# 6. Cleanup when done
os.unlink(ca_cert_path)
```

## Best Practices

### Frontend

1. **Always Check Status Before Operations:**
   ```typescript
   async function performOperation() {
     const status = await checkCredentialStatus();
     if (status.status === 'expired') {
       redirectToLogin();
       return;
     }
     // Proceed with operation
   }
   ```

2. **Show Expiration Warnings:**
   - Display countdown when <10 minutes remaining
   - Provide "Refresh Credentials" button
   - Don't interrupt user mid-operation

3. **Handle 401 Gracefully:**
   - Don't show technical error messages
   - Preserve user's work when possible
   - Provide clear next steps

### Backend

1. **Consistent Error Responses:**
   - Always use 401 for authentication errors
   - Include actionable error messages
   - Add headers for frontend to detect error type

2. **Cleanup Resources:**
   - Remove expired credentials regularly
   - Clean up temp CA cert files
   - Close K8s client connections

3. **Logging:**
   - Log authentication attempts
   - Log credential expiration events
   - Don't log sensitive credential data

## Troubleshooting

### "Credentials expired" immediately after login

**Cause:** System clock skew or incorrect TTL
**Solution:** Check server time synchronization, verify TTL is set to 3600s

### "No cluster selected" after re-authentication

**Cause:** Session state cleared on re-auth
**Solution:** Frontend should re-select cluster after successful re-authentication

### SSL certificate verification failed

**Cause:** CA certificate not properly decoded or temp file not accessible
**Solution:** Check file permissions, verify base64 decoding, ensure temp directory is writable

### Bearer token invalid

**Cause:** Token expired (60s lifetime) or credentials expired
**Solution:** Tokens are regenerated per request, check credential expiration first
