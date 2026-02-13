# Kubeconfig Streaming Authentication Design

## Context
- Current kubeconfig auth requires file path access
- Container cannot access host filesystem
- Need to stream kubeconfig content from browser to backend

## Assumptions
- User can paste kubeconfig content or upload file via browser
- Kubeconfig may contain multiple contexts
- Session-based storage with TTL for security

## Proposed Design

### Frontend Changes

**[`LoginForm.tsx`](frontend/src/components/LoginForm.tsx)**
- Add file upload input for kubeconfig file
- Add textarea for pasting kubeconfig content
- After upload, call `/api/credentials/kubeconfig/parse` to get contexts
- Display context dropdown for selection
- Submit selected context to `/api/credentials/kubeconfig`

**New Types in [`credentials.ts`](frontend/src/types/credentials.ts)**
```typescript
interface KubeconfigUpload {
  content: string;  // Raw YAML content
}

interface KubeconfigParseResponse {
  contexts: { name: string; cluster: string }[];
  currentContext: string | null;
}
```

### Backend Changes

**[`credentials.py`](backend/api/credentials.py)**

New endpoints:
- `POST /api/credentials/kubeconfig/parse` - Parse kubeconfig content, return contexts
- `POST /api/credentials/kubeconfig` - Modified to accept content instead of path

**[`local_k8s_auth.py`](backend/local_k8s_auth.py)**

New functions:
- `parse_kubeconfig_content(content: str)` - Parse YAML content, return contexts
- `validate_kubeconfig_content(content: str)` - Validate structure
- `get_k8s_client_from_content(content: str, context: str)` - Create client from content

### Data Flow

```
1. User uploads/pastes kubeconfig → Frontend
2. Frontend calls POST /api/credentials/kubeconfig/parse with content
3. Backend parses YAML, returns list of contexts
4. User selects context from dropdown
5. Frontend calls POST /api/credentials/kubeconfig with content + selected context
6. Backend stores in CredentialStore, returns session ID
```

## Tasks

1. [ ] Add `KubeconfigUpload` and `KubeconfigParseResponse` types to [`credentials.ts`](frontend/src/types/credentials.ts)
2. [ ] Add `parseKubeconfig` API method to [`api.ts`](frontend/src/services/api.ts)
3. [ ] Modify `loginKubeconfig` to accept content instead of path
4. [ ] Update [`LoginForm.tsx`](frontend/src/components/LoginForm.tsx) with file upload/textarea
5. [ ] Add context selection dropdown after kubeconfig parse
6. [ ] Add `parse_kubeconfig_content` function to [`local_k8s_auth.py`](backend/local_k8s_auth.py)
7. [ ] Add `POST /api/credentials/kubeconfig/parse` endpoint to [`credentials.py`](backend/api/credentials.py)
8. [ ] Modify `POST /api/credentials/kubeconfig` to accept content + context
9. [ ] Update [`useCredentials.ts`](frontend/src/hooks/useCredentials.ts) hook for new flow
10. [ ] Add tests for new endpoints

## Acceptance Criteria

- User can upload kubeconfig file via file picker
- User can paste kubeconfig content into textarea
- After upload, available contexts are displayed in dropdown
- User can select a context and authenticate
- Backend validates kubeconfig without filesystem access
- Session is created with selected context
- Works when backend runs in Kubernetes container
