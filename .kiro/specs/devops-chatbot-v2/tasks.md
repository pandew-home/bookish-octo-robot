# Implementation Plan: DevOps Chatbot v2.0

## Overview

This implementation plan converts the v2.0 design into a series of incremental coding tasks. The plan reuses code from v1 (improved-sniffle) where applicable, particularly for shared libraries and components that don't require changes. The focus is on implementing the new authentication flow (Kion credentials), cluster discovery, and simplified architecture without MCP protocol.

## Programming Languages

- **Backend**: Python 3.11+ with FastAPI
- **Frontend**: TypeScript with React 18+
- **Testing**: Hypothesis (Python), fast-check (TypeScript)

## Tasks

- [x] 1. Set up project structure and reuse v1 shared libraries
  - Create bookish-octo-robot project structure (backend/, frontend/, libs/, k8s/, k8sgpt/, docker/)
  - Copy shared libraries from v1: devops-rag, devops-k8s, devops-prompts, devops-kb
  - Update library imports to remove MCP dependencies
  - Create requirements.txt and package.json
  - _Requirements: 15.2, 15.3_

- [ ] 2. Implement Kion credential management (backend)
  - [x] 2.1 Create CredentialStore class with TTL-based expiration
    - Implement in-memory storage with threading.Lock for thread safety
    - Add store(), get(), cleanup_expired(), remove() methods
    - Implement automatic eviction of oldest expired credentials
    - _Requirements: 1.2, 1.5, 1.6, 17.6_
  
  - [ ]* 2.2 Write property test for credential storage round trip
    - **Property 2: Credential Storage Round Trip**
    - **Validates: Requirements 1.2**
  
  - [ ]* 2.3 Write property test for credential isolation
    - **Property 3: Credential Isolation**
    - **Validates: Requirements 1.5**

- [ ] 3. Implement AWS STS authentication (backend)
  - [x] 3.1 Create EKS token generator using boto3 RequestSigner
    - Implement get_eks_bearer_token() function
    - Generate presigned GetCallerIdentity URL
    - Format as k8s-aws-v1.{base64_encoded_signed_url}
    - _Requirements: 2.3_
  
  - [x] 3.2 Create credential validation via STS GetCallerIdentity
    - Implement validate_credentials() function
    - Extract user ARN and account ID from response
    - Handle invalid credentials with descriptive errors
    - _Requirements: 1.1, 1.4_
  
  - [ ]* 3.3 Write property test for credential validation consistency
    - **Property 1: Credential Validation Consistency**
    - **Validates: Requirements 1.1, 1.4**
  
  - [ ]* 3.4 Write property test for bearer token generation
    - **Property 6: Bearer Token Generation**
    - **Validates: Requirements 2.3**


- [ ] 4. Implement cluster discovery and K8s client factory (backend)
  - [x] 4.1 Create cluster discovery using EKS ListClusters
    - Implement discover_clusters() async function
    - Use user's Kion credentials with boto3
    - Return cluster metadata (name, endpoint, version, status, region, CA data)
    - Implement 300-second caching
    - _Requirements: 2.1, 2.2, 2.6_
  
  - [x] 4.2 Create K8s client factory
    - Implement get_k8s_clients() function
    - Generate bearer token and configure K8s API client
    - Write CA certificate to temp file
    - Return dict with CoreV1Api, AppsV1Api, CustomObjectsApi, NetworkingV1Api, RbacAuthorizationV1Api
    - _Requirements: 2.4_
  
  - [ ]* 4.3 Write property test for cluster metadata completeness
    - **Property 5: Cluster Metadata Completeness**
    - **Validates: Requirements 2.2**
  
  - [ ]* 4.4 Write property test for K8s client configuration
    - **Property 7: K8s Client Configuration**
    - **Validates: Requirements 2.4**
  
  - [ ]* 4.5 Write property test for cache consistency
    - **Property 8: Cache Consistency**
    - **Validates: Requirements 2.6, 6.5, 9.4, 9.5**

- [ ] 5. Implement authentication API endpoints (backend)
  - [x] 5.1 Create POST /api/credentials/aws endpoint
    - Accept Kion credentials (access key, secret key, session token, region)
    - Validate via STS GetCallerIdentity
    - Store in CredentialStore with TTL
    - Return success with session ID
    - _Requirements: 1.1, 1.2, 1.4_
  
  - [x] 5.2 Create GET /api/credentials/aws/status endpoint
    - Return credential status (active, expiring_soon, expired, no_credentials)
    - Include TTL remaining in seconds
    - _Requirements: 1.3_
  
  - [x] 5.3 Create DELETE /api/credentials/aws endpoint
    - Remove credentials from CredentialStore
    - _Requirements: 1.6_
  
  - [ ]* 5.4 Write unit tests for credential API endpoints
    - Test valid credential submission
    - Test invalid credential rejection
    - Test status endpoint responses
    - Test credential deletion
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_


- [ ] 6. Implement cluster management API endpoints (backend)
  - [x] 6.1 Create GET /api/clusters endpoint
    - Discover clusters using user's credentials
    - Return list of accessible clusters
    - Handle discovery failures gracefully
    - _Requirements: 2.1, 2.2, 2.5_
  
  - [x] 6.2 Create POST /api/clusters/select endpoint
    - Generate bearer token for selected cluster
    - Create K8s API clients
    - Store selected cluster in session
    - _Requirements: 2.3, 2.4_
  
  - [ ]* 6.3 Write unit tests for cluster API endpoints
    - Test cluster discovery
    - Test cluster selection
    - Test error handling for discovery failures
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 7. Reuse and adapt query router from v1 (backend)
  - [x] 7.1 Copy QueryRouter from v1 and remove MCP dependencies
    - Update category enum (remove MCP-specific categories)
    - Keep deterministic pattern matching logic
    - Update keyword lists for v2 categories
    - _Requirements: 4.1, 4.2, 4.3_
  
  - [x] 7.2 Integrate unsafe pattern detection from v1 InputSanitizer
    - Reuse input sanitizer for query validation
    - Block shell commands, code execution, credential access
    - _Requirements: 4.4, 8.2, 8.3, 8.4_
  
  - [ ]* 7.3 Write property test for query classification determinism
    - **Property 12: Query Classification Determinism**
    - **Validates: Requirements 4.1**
  
  - [ ]* 7.4 Write property test for multi-pattern priority
    - **Property 13: Multi-Pattern Priority**
    - **Validates: Requirements 4.3**
  
  - [ ]* 7.5 Write property test for unsafe query rejection
    - **Property 14: Unsafe Query Rejection**
    - **Validates: Requirements 4.4, 8.2, 8.3, 8.4**

- [ ] 8. Checkpoint - Ensure authentication and routing tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 9. Implement enrichment engine (backend)
  - [x] 9.1 Create EnrichmentEngine class with execute() method
    - Implement _enrich_pods() for pod status, events, logs
    - Implement _enrich_deployments() for deployment status, replicas, events
    - Implement _enrich_services() for service endpoints, ingress rules
    - Implement _enrich_nodes() for node conditions, capacity, taints
    - Implement _enrich_storage() for PVC status, storage class
    - Implement _enrich_argocd() for ArgoCD Application CRDs
    - Implement _enrich_security() for RBAC roles, service accounts
    - Implement _enrich_aws() with 3-call limit
    - Handle RBAC 403 errors gracefully
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  
  - [ ]* 9.2 Write property test for CRD reading on enrichment
    - **Property 15: CRD Reading on Enrichment**
    - **Validates: Requirements 3.1, 5.1, 12.1**
  
  - [ ]* 9.3 Write property test for AWS API call limiting
    - **Property 16: AWS API Call Limiting**
    - **Validates: Requirements 5.6, 9.3**
  
  - [ ]* 9.4 Write unit tests for category-specific enrichment
    - Test pod enrichment retrieves status, events, logs
    - Test deployment enrichment retrieves status, replicas
    - Test ArgoCD enrichment reads Application CRDs
    - Test AWS enrichment makes boto3 calls
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

- [ ] 10. Implement K8sGPT Result CRD reading (backend)
  - [x] 10.1 Create function to read K8sGPT Result CRDs
    - Use CustomObjectsApi to list Result CRDs
    - Parse CRD structure (name, kind, namespace, severity, problem, solution, analyzer, timestamp)
    - Handle missing CRDs gracefully
    - _Requirements: 3.1, 12.1_
  
  - [x] 10.2 Implement weather state calculation
    - Calculate weather state based on severity and count
    - Classify as Sunny, Partly Cloudy, Cloudy, Rainy, or Stormy
    - Sort issues by severity and return top 5
    - Include cluster metadata in response
    - _Requirements: 3.2, 3.3, 3.4, 3.5_
  
  - [ ]* 10.3 Write property test for weather state classification
    - **Property 9: Weather State Classification**
    - **Validates: Requirements 3.2, 3.3**
  
  - [ ]* 10.4 Write property test for top issues sorting
    - **Property 10: Top Issues Sorting**
    - **Validates: Requirements 3.4**
  
  - [ ]* 10.5 Write property test for weather metadata completeness
    - **Property 11: Weather Metadata Completeness**
    - **Validates: Requirements 3.5**


- [ ] 11. Reuse RAG engine from v1 (backend)
  - [x] 11.1 Copy RAG engine from devops-rag library
    - Reuse FAISS vector store implementation
    - Reuse embedding generation with sentence-transformers
    - Reuse semantic search with top-k retrieval
    - Implement 3600-second embedding cache
    - _Requirements: 6.1, 6.2, 6.3, 6.5_
  
  - [ ]* 11.2 Write property test for RAG retrieval filtering
    - **Property 17: RAG Retrieval Filtering**
    - **Validates: Requirements 6.3**
  
  - [ ]* 11.3 Write property test for KB citation inclusion
    - **Property 18: KB Citation Inclusion**
    - **Validates: Requirements 6.4, 7.5**

- [x] 12. Reuse and adapt prompt template engine from v1 (backend)
  - [x] 12.1 Copy prompt templates from v1
    - Reuse base template with system prompt
    - Reuse category-specific templates (troubleshooting, deployment, networking, security, gitops)
    - Update templates to reference K8sGPT Results instead of MCP
    - _Requirements: 7.1, 7.2_
  
  - [x] 12.2 Implement template rendering with Jinja2
    - Render structured prompts with cluster context, KB results, query
    - Include query classification, K8sGPT findings, K8s API data, AWS context
    - _Requirements: 7.1, 7.2_
  
  - [ ]* 12.3 Write property test for prompt context completeness
    - **Property 19: Prompt Context Completeness**
    - **Validates: Requirements 7.2**

- [x] 13. Implement LLM client and response generation (backend)
  - [x] 13.1 Reuse LLM client from v1
    - Copy LLM client from devops-rag library
    - Support Anthropic, OpenAI, Ollama providers
    - Implement 4096 token limit enforcement
    - Add retry logic with exponential backoff
    - _Requirements: 7.3, 9.6, 9.7_
  
  - [x] 13.2 Implement response parsing and safety detection
    - Parse LLM response for recommendations, commands, warnings
    - Detect unsafe commands (delete, remove, destroy, drop)
    - Add safety warnings to response
    - Include citations for KB entries
    - Highlight K8sGPT findings prominently
    - _Requirements: 7.4, 7.5, 7.6, 7.8_
  
  - [ ]* 13.3 Write property test for token limit enforcement
    - **Property 20: Token Limit Enforcement**
    - **Validates: Requirements 7.3, 9.7**
  
  - [ ]* 13.4 Write property test for response safety detection
    - **Property 21: Response Safety Detection**
    - **Validates: Requirements 7.8**


- [ ] 14. Reuse input validation and rate limiting from v1 (backend)
  - [x] 14.1 Copy InputSanitizer from v1
    - Reuse query length validation (1-2000 characters)
    - Reuse SQL injection detection
    - Reuse shell command injection detection
    - Reuse credential access detection
    - Reuse sanitization for logging
    - Add AWS credential format validation
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  
  - [x] 14.2 Copy RateLimiter from v1
    - Reuse per-user rate limiting (20 queries/min for chat)
    - Reuse 429 error responses with retry-after headers
    - _Requirements: 9.1, 9.2_
  
  - [ ]* 14.3 Write property test for query length validation
    - **Property 22: Query Length Validation**
    - **Validates: Requirements 8.1**
  
  - [ ]* 14.4 Write property test for input sanitization
    - **Property 23: Input Sanitization**
    - **Validates: Requirements 8.5**
  
  - [ ]* 14.5 Write property test for credential format validation
    - **Property 24: Credential Format Validation**
    - **Validates: Requirements 8.6**
  
  - [ ]* 14.6 Write property test for rate limit enforcement
    - **Property 25: Rate Limit Enforcement**
    - **Validates: Requirements 9.1**

- [ ] 15. Reuse conversation history manager from v1 (backend)
  - [x] 15.1 Copy ConversationHistoryManager from v1
    - Reuse per-user conversation storage on PVC
    - Adapt for per-cluster history isolation
    - Reuse 50-message limit per user per cluster
    - Reuse auto-summarization every 7 messages
    - Reuse 24-hour persistence after session end
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  
  - [ ]* 15.2 Write property test for conversation history retrieval
    - **Property 26: Conversation History Retrieval**
    - **Validates: Requirements 10.1**
  
  - [ ]* 15.3 Write property test for conversation history storage
    - **Property 27: Conversation History Storage**
    - **Validates: Requirements 10.2**
  
  - [ ]* 15.4 Write property test for conversation history isolation
    - **Property 28: Conversation History Isolation**
    - **Validates: Requirements 10.3**
  
  - [ ]* 15.5 Write property test for conversation history limit
    - **Property 29: Conversation History Limit**
    - **Validates: Requirements 10.4**


- [ ] 16. Implement knowledge base management (backend)
  - [x] 16.1 Reuse KB management from v1 devops-kb library
    - Copy solution storage and retrieval
    - Copy FAISS index management
    - Adapt for shared PVC storage
    - _Requirements: 11.2, 11.3, 11.4, 11.5_
  
  - [x] 16.2 Implement solution validation and submission
    - Validate required fields (title, description, tags)
    - Generate embeddings for new solutions
    - Update FAISS index immediately
    - Store on shared PVC
    - _Requirements: 11.1, 11.2, 11.3_
  
  - [ ]* 16.3 Write property test for solution validation
    - **Property 30: Solution Validation**
    - **Validates: Requirements 11.1**
  
  - [ ]* 16.4 Write property test for solution storage and indexing
    - **Property 31: Solution Storage and Indexing**
    - **Validates: Requirements 11.2, 11.3, 11.4**
  
  - [ ]* 16.5 Write property test for shared knowledge base
    - **Property 32: Shared Knowledge Base**
    - **Validates: Requirements 11.5**

- [ ] 17. Implement chat API endpoint (backend)
  - [x] 17.1 Create POST /api/chat endpoint
    - Get user's K8s clients for selected cluster
    - Read K8sGPT Result CRDs
    - Classify query and build enrichment plan
    - Execute enrichment with targeted K8s/AWS API calls
    - Retrieve KB results via RAG
    - Render prompt with template engine
    - Send to LLM and parse response
    - Save conversation to history
    - Return response with citations, K8sGPT findings, safety notices
    - _Requirements: 4.1, 5.1, 6.1, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.8, 10.2, 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [ ]* 17.2 Write integration test for end-to-end chat flow
    - Test login → cluster selection → query → response
    - Test K8sGPT Result integration
    - Test KB citation inclusion
    - Test safety warning display
    - _Requirements: 7.1, 7.2, 7.5, 7.6, 7.8, 12.3, 12.4, 12.5_

- [ ] 18. Checkpoint - Ensure backend core functionality tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 19. Implement weather and results API endpoints (backend)
  - [x] 19.1 Create GET /api/weather endpoint
    - Read K8sGPT Result CRDs from selected cluster
    - Make lightweight K8s API calls (node count, pod summary)
    - Calculate weather state
    - Return top issues, cluster info, tool versions
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [x] 19.2 Create GET /api/weather/details endpoint
    - Return detailed cluster breakdown
    - Include all K8sGPT Results with metadata
    - _Requirements: 3.5_
  
  - [x] 19.3 Create GET /api/results endpoint
    - List all K8sGPT Result CRDs for selected cluster
    - Filter by severity, namespace, kind
    - _Requirements: 12.1, 12.2_
  
  - [x] 19.4 Create GET /api/results/{id} endpoint
    - Return specific Result with enrichment
    - Include analyzer metadata
    - _Requirements: 12.5_
  
  - [x]* 19.5 Write unit tests for weather and results endpoints
    - Test weather calculation
    - Test results filtering
    - Test metadata inclusion
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 12.2, 12.5_

- [x] 20. Implement solutions API endpoints (backend)
  - [x] 20.1 Create POST /api/solutions endpoint
    - Validate solution fields
    - Generate embeddings
    - Store in KB on shared PVC
    - Update FAISS index
    - _Requirements: 11.1, 11.2, 11.3_
  
  - [x] 20.2 Create GET /api/solutions endpoint
    - List solutions with pagination
    - Filter by tags
    - _Requirements: 11.4, 11.5_
  
  - [x] 20.3 Create GET /api/kb/search endpoint
    - Perform semantic search via RAG
    - Return top-k results with similarity scores
    - _Requirements: 6.2, 6.3_
  
  - [x]* 20.4 Write unit tests for solutions endpoints
    - Test solution submission
    - Test solution retrieval
    - Test KB search
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_


- [x] 21. Implement conversation history API endpoints (backend)
  - [x] 21.1 Create GET /api/chat/history endpoint
    - Return conversation history for user and selected cluster
    - Limit to last 50 messages
    - _Requirements: 10.1, 10.4_
  
  - [x] 21.2 Create POST /api/chat/export endpoint
    - Generate LLM summary of conversation
    - Format as markdown with problem, investigation, root cause, solution, verification
    - _Requirements: 10.6_
  
  - [ ]* 21.3 Write unit tests for conversation history endpoints
    - Test history retrieval
    - Test export formatting
    - _Requirements: 10.1, 10.4, 10.6_

- [ ] 22. Implement multi-cluster support (backend)
  - [x] 22.1 Add cluster switching logic
    - Generate new bearer token for new cluster
    - Reconfigure K8s API clients
    - Switch conversation history to new cluster
    - Clear cached cluster-specific data
    - _Requirements: 13.1, 13.2, 13.3, 13.4_
  
  - [ ]* 22.2 Write property test for cluster switch token regeneration
    - **Property 36: Cluster Switch Token Regeneration**
    - **Validates: Requirements 13.1**
  
  - [ ]* 22.3 Write property test for cluster switch client reconfiguration
    - **Property 37: Cluster Switch Client Reconfiguration**
    - **Validates: Requirements 13.2**
  
  - [ ]* 22.4 Write property test for per-cluster history isolation
    - **Property 38: Per-Cluster History Isolation**
    - **Validates: Requirements 13.3**
  
  - [ ]* 22.5 Write property test for cluster switch cache invalidation
    - **Property 39: Cluster Switch Cache Invalidation**
    - **Validates: Requirements 13.4**

- [x] 23. Implement startup validation and health checks (backend)
  - [x] 23.1 Reuse and adapt StartupValidator from v1
    - Validate required environment variables (LLM_API_KEY, DEFAULT_REGION)
    - Verify PVC mounted and writable
    - Load and validate prompt templates
    - Initialize or create FAISS index
    - Exit with non-zero code on failure
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_
  
  - [x] 23.2 Create health check endpoints
    - Implement GET /api/health for liveness
    - Implement GET /api/health/ready for readiness (returns 503 until validation complete)
    - _Requirements: 16.6, 16.7_
  
  - [ ]* 23.3 Write property tests for startup validation
    - **Property 41: Startup Validation Failure**
    - **Property 42: PVC Validation**
    - **Property 43: Template Validation**
    - **Property 44: FAISS Index Initialization**
    - **Property 45: Readiness After Validation**
    - **Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.7**


- [x] 24. Implement error handling and observability (backend)
  - [x] 24.1 Implement comprehensive error logging
    - Log errors with severity, timestamp, user ID, stack trace
    - Log AWS API calls with duration and response status
    - Log LLM API calls with token counts and latency
    - Return user-friendly error messages without internal details
    - _Requirements: 17.1, 17.2, 17.3, 17.4_
  
  - [x] 24.2 Implement Kubernetes API retry logic
    - Retry connection failures with exponential backoff
    - Handle RBAC 403 errors gracefully
    - _Requirements: 17.7_
  
  - [x] 24.3 Add Prometheus metrics endpoints
    - Expose metrics for query latency, error rates, API call counts
    - _Requirements: 17.5_
  
  - [ ]* 24.4 Write property tests for error handling
    - **Property 46: Error Logging Completeness**
    - **Property 47: User-Friendly Error Messages**
    - **Property 48: API Call Logging**
    - **Property 49: Credential Store Eviction**
    - **Property 50: Kubernetes API Retry with Backoff**
    - **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.6, 17.7**

- [x] 25. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 26. Implement frontend LoginForm component
  - [x] 26.1 Create LoginForm component with Kion credential fields
    - Add fields for access key, secret key, session token, region
    - Implement format validation
    - Add help text with link to Kion console
    - Handle submission to POST /api/credentials/aws
    - _Requirements: 14.1_
  
  - [x]* 26.2 Write unit tests for LoginForm
    - Test credential format validation
    - Test submission handling
    - Test error display
    - _Requirements: 14.1_

- [x] 27. Implement frontend ClusterSelector component
  - [x] 27.1 Create ClusterSelector dropdown component
    - Display cluster name, region, version
    - Implement environment-based theming (dev/staging/prod colors)
    - Handle cluster selection via POST /api/clusters/select
    - _Requirements: 14.2, 13.5_
  
  - [x]* 27.2 Write unit tests for ClusterSelector
    - Test cluster list rendering
    - Test selection handling
    - Test theming
    - _Requirements: 14.2, 13.5_


- [x] 28. Reuse and adapt frontend components from v1
  - [x] 28.1 Copy CredentialBadge component from v1
    - Reuse TTL countdown display
    - Reuse color-coded status (green/orange/red/gray)
    - Update to poll GET /api/credentials/aws/status
    - _Requirements: 14.5_
  
  - [x] 28.2 Copy and adapt WeatherWidget component from v1
    - Update data source to GET /api/weather
    - Update weather state icons and colors
    - Add quick action buttons (View Pods, Check Events, Ask About This)
    - Implement 60-second polling
    - Preserve previous data during refresh
    - _Requirements: 14.3, 14.4_
  
  - [x] 28.3 Copy ChatInterface component from v1
    - Reuse message history display
    - Reuse copy buttons for commands
    - Reuse safety warning display
    - Add "Save to KB" button on assistant messages
    - Update to use POST /api/chat
    - _Requirements: 14.3_
  
  - [x]* 28.4 Write unit tests for reused components
    - Test CredentialBadge status display
    - Test WeatherWidget polling and display
    - Test ChatInterface message rendering
    - _Requirements: 14.3, 14.4, 14.5_

- [x] 29. Implement frontend ResultsPanel component
  - [x] 29.1 Create ResultsPanel component
    - Display K8sGPT Result CRDs with severity indicators
    - Add filtering by severity, namespace, kind
    - Add "Ask About This" button for each result
    - Fetch data from GET /api/results
    - _Requirements: 14.6_
  
  - [x]* 29.2 Write unit tests for ResultsPanel
    - Test result rendering
    - Test filtering
    - Test quick actions
    - _Requirements: 14.6_

- [x] 30. Implement frontend SolutionSubmitDialog component
  - [x] 30.1 Reuse and adapt SolutionSubmitDialog from v1
    - Add conversationId prop for pre-filling from chat
    - Implement validation for required fields
    - Submit to POST /api/solutions
    - Display success/error feedback
    - _Requirements: 14.7_
  
  - [x]* 30.2 Write unit tests for SolutionSubmitDialog
    - Test field validation
    - Test submission
    - Test pre-fill from conversation
    - _Requirements: 14.7_


- [x] 31. Implement frontend hooks and state management
  - [x] 31.1 Create useCredentials hook
    - Manage credential submission, status polling, expiration
    - Handle re-authentication flow
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  
  - [x] 31.2 Create useCluster hook
    - Manage cluster discovery, selection, switching
    - Handle cluster-specific state
    - _Requirements: 2.1, 2.2, 2.3, 13.1, 13.2_
  
  - [x] 31.3 Create useChat hook
    - Manage message submission, history, export
    - Handle conversation state
    - _Requirements: 7.1, 10.1, 10.2_
  
  - [x] 31.4 Create useWeather hook
    - Manage weather polling, state updates
    - Handle weather data caching
    - _Requirements: 3.1, 3.2, 3.3_
  
  - [x]* 31.5 Write unit tests for hooks
    - Test useCredentials state management
    - Test useCluster switching logic
    - Test useChat message handling
    - Test useWeather polling
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 3.1, 7.1, 10.1_

- [x] 32. Implement frontend App component and routing
  - [x] 32.1 Create main App component
    - Implement authentication flow (LoginForm → ClusterSelector → Main Interface)
    - Wire up all components
    - Implement environment-based theming
    - _Requirements: 14.1, 14.2, 14.3_
  
  - [ ]* 32.2 Write integration tests for frontend flows
    - Test login flow
    - Test cluster selection flow
    - Test chat interaction flow
    - Test solution submission flow
    - _Requirements: 14.1, 14.2, 14.3, 14.7_

- [x] 33. Checkpoint - Ensure all frontend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 34. Create Kubernetes manifests for app deployment
  - [x] 34.1 Create deployment.yaml for chatbot app
    - Single deployment with frontend + backend container
    - Resource requests/limits (500m/1Gi request, 1000m/2Gi limit)
    - Environment variables (LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, DEFAULT_REGION)
    - Volume mount for shared PVC at /data
    - Liveness and readiness probes
    - Security context (non-root UID 1000, read-only root filesystem)
    - _Requirements: 15.2, 15.3, 16.6_
  
  - [x] 34.2 Create pvc.yaml for shared knowledge base
    - 10Gi ReadWriteOnce PVC
    - _Requirements: 15.3_
  
  - [x] 34.3 Create service.yaml and ingress.yaml
    - Service exposing port 80
    - Ingress with internal ALB and TLS termination
    - _Requirements: 15.4_
  
  - [x] 34.4 Create secrets.yaml for sensitive configuration
    - LLM API key
    - _Requirements: 15.2_


- [x] 35. Create K8sGPT Operator manifests for per-cluster deployment
  - [x] 35.1 Create argocd-application.yaml for operator deployment
    - ArgoCD Application pointing to K8sGPT Helm chart
    - Target namespace: k8sgpt-operator-system
    - Auto-sync enabled
    - _Requirements: 15.1_
  
  - [x] 35.2 Create k8sgpt-cr.yaml for K8sGPT custom resource
    - Configure AI backend (OpenAI or Amazon Bedrock)
    - Set model to gpt-4o-mini for cost efficiency
    - Configure scanning filters
    - _Requirements: 15.1, 15.5_
  
  - [x] 35.3 Create rbac.yaml for operator permissions
    - ClusterRole with read-only access to cluster resources
    - Read/write access to K8sGPT Result CRDs
    - _Requirements: 15.5_

- [x] 36. Create Docker configuration
  - [x] 36.1 Create multi-stage Dockerfile
    - Stage 1: Build frontend with Node 20
    - Stage 2: Python 3.11-slim with nginx + supervisor
    - Install backend dependencies and shared libraries
    - Copy frontend build to /var/www/html
    - Run as UID 1000
    - _Requirements: 15.2_
  
  - [x] 36.2 Create nginx.conf
    - Serve frontend static files
    - Proxy /api/* to FastAPI backend
    - _Requirements: 15.2_
  
  - [x] 36.3 Create supervisord.conf
    - Manage nginx and FastAPI processes
    - _Requirements: 15.2_

- [x] 37. Create configuration and documentation
  - [x] 37.1 Create requirements.txt for backend
    - FastAPI, uvicorn, boto3, kubernetes, hypothesis, pytest
    - Dependencies for shared libraries
    - _Requirements: 15.2_
  
  - [x] 37.2 Create package.json for frontend
    - React, TypeScript, MUI, axios, fast-check, jest
    - _Requirements: 15.2_
  
  - [x] 37.3 Create README.md with setup instructions
    - Prerequisites (Kion, EKS clusters, K8sGPT operator)
    - Local development setup
    - Deployment instructions
    - Architecture overview
    - _Requirements: 15.1, 15.2_
  
  - [x] 37.4 Create environment variable documentation
    - Required: LLM_API_KEY, DEFAULT_REGION
    - Optional: KB_SEEDING_ENABLED, KB_FORCE_RESEED
    - _Requirements: 16.1_


- [x] 38. Integration testing and end-to-end validation
  - [x] 38.1 Write end-to-end integration tests
    - Test complete authentication flow (Kion creds → cluster discovery → selection)
    - Test complete chat flow (query → enrichment → RAG → LLM → response)
    - Test weather monitoring flow (polling → CRD reading → calculation → display)
    - Test solution submission flow (chat → save to KB → retrieval)
    - Test cluster switching flow (select new cluster → token regeneration → history switch)
    - _Requirements: 1.1, 1.2, 2.1, 2.3, 3.1, 3.2, 7.1, 11.2, 13.1, 13.3_
  
  - [x] 38.2 Test error handling scenarios
    - Test credential expiration handling
    - Test cluster discovery failures
    - Test K8sGPT CRD read failures
    - Test RBAC permission errors
    - Test LLM API failures
    - Test rate limit enforcement
    - _Requirements: 1.3, 2.5, 3.6, 5.7, 9.1, 17.2, 17.7_
  
  - [x] 38.3 Test multi-user scenarios
    - Test credential isolation between users
    - Test conversation history isolation
    - Test shared knowledge base access
    - _Requirements: 1.5, 10.3, 11.5_

- [x] 39. Final checkpoint - Ensure all tests pass and system is ready for deployment
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 40. Implement async timeout enforcement in EnrichmentEngine
  - Wrap asyncio.gather in asyncio.wait_for(self.timeout) to prevent hanging on slow K8s API calls
  - Add timeout handling to _enrich_pods, _enrich_deployments, etc.
  - _Requirements: 5.8_

- [ ] 41. Fix AWS credential validation pattern
  - Update input_sanitizer.py to accept ASIA* (temporary) credentials in addition to AKIA*
  - Pattern: ^A[SK]IA[0-9A-Z]{16}$
  - _Requirements: 8.6_

## Notes

- Tasks marked with `*` are optional property-based tests and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties with 100+ iterations
- Unit tests validate specific examples, edge cases, and error conditions
- Integration tests validate end-to-end flows across components
- Reuse v1 code extensively: shared libraries (devops-rag, devops-k8s, devops-prompts, devops-kb), InputSanitizer, RateLimiter, ConversationHistoryManager, StartupValidator, LLM client, RAG engine, prompt templates, frontend components (CredentialBadge, ChatInterface, SolutionSubmitDialog)
- New v2 components: CredentialStore, EKS token generator, cluster discovery, K8s client factory, LoginForm, ClusterSelector, ResultsPanel
- Removed from v1: OIDC authentication, JWT handling, MCP protocol, MCP server pods, per-cluster deployments
