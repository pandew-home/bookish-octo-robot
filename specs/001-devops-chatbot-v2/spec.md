# Requirements Document

## Introduction

DevOps Chatbot v2.0 is a simplified, decoupled architecture for Kubernetes cluster diagnostics and troubleshooting. The system separates cluster diagnostics (K8sGPT Operator deployed per cluster) from the user-facing application (React + FastAPI deployed once in a common cluster). The system provides real-time cluster health monitoring, RAG-powered troubleshooting chat, and multi-cluster support through Kion-based AWS credential management.

## Glossary

- **System**: The DevOps Chatbot v2.0 application (frontend + backend)
- **Operator**: The K8sGPT Operator deployed per monitored cluster
- **User**: A DevOps engineer or developer using the chatbot
- **Kion**: AWS credential management system providing temporary credentials
- **Result_CRD**: Kubernetes Custom Resource Definition created by K8sGPT Operator containing diagnostic results
- **Weather_State**: Cluster health status (Sunny, Partly_Cloudy, Cloudy, Stormy)
- **Query_Router**: Component that classifies user queries using deterministic pattern matching
- **Enrichment_Engine**: Component that gathers additional context from K8s/AWS APIs
- **RAG_Engine**: Retrieval-Augmented Generation engine using FAISS for semantic search
- **Knowledge_Base**: Shared PVC containing team-wide troubleshooting solutions and documentation
- **Bearer_Token**: EKS authentication token generated from STS credentials
- **Credential_Store**: In-memory storage for per-user AWS credentials with TTL
- **Target_Cluster**: The specific EKS cluster selected by the user for operations

## Requirements

### Requirement 1: User Authentication and Credential Management

**User Story:** As a DevOps engineer, I want to authenticate using my Kion AWS credentials, so that I can securely access multiple EKS clusters without complex OIDC flows.

#### Acceptance Criteria

1. WHEN a User submits Kion AWS credentials (access key, secret key, session token, region), THE System SHALL validate them via STS GetCallerIdentity
2. WHEN credentials are validated, THE System SHALL store them in the Credential_Store with a TTL of 3600 seconds
3. WHEN credentials expire, THE System SHALL notify the User and prompt for re-authentication
4. WHEN invalid credentials are submitted, THE System SHALL return a descriptive error message and reject the authentication attempt
5. THE System SHALL maintain separate credential entries for each User in the Credential_Store
6. WHEN a User's session ends, THE System SHALL remove their credentials from the Credential_Store

### Requirement 2: Cluster Discovery and Selection

**User Story:** As a DevOps engineer, I want to discover and select from available EKS clusters, so that I can monitor and troubleshoot specific clusters.

#### Acceptance Criteria

1. WHEN a User is authenticated, THE System SHALL discover available clusters using EKS ListClusters API with the User's credentials
2. WHEN clusters are discovered, THE System SHALL present them in a selectable list with cluster name and region
3. WHEN a User selects a Target_Cluster, THE System SHALL generate an EKS Bearer_Token using STS credentials
4. WHEN the Bearer_Token is generated, THE System SHALL configure a Kubernetes API client for the Target_Cluster
5. IF cluster discovery fails, THEN THE System SHALL return an error message and allow credential re-entry
6. THE System SHALL cache the cluster list for 300 seconds to minimize API calls

### Requirement 3: Real-Time Cluster Health Monitoring

**User Story:** As a DevOps engineer, I want to see real-time cluster health status, so that I can quickly identify issues requiring attention.

#### Acceptance Criteria

1. WHEN the frontend polls the weather endpoint, THE System SHALL read Result_CRDs from the Target_Cluster
2. WHEN Result_CRDs are retrieved, THE System SHALL calculate Weather_State based on severity and count of issues
3. THE System SHALL classify Weather_State as Sunny (0 critical issues), Partly_Cloudy (1-2 warnings), Cloudy (3-5 warnings or 1 critical), or Stormy (2+ critical or 6+ warnings)
4. WHEN Weather_State is calculated, THE System SHALL return the top 5 issues sorted by severity
5. THE System SHALL include cluster metadata (name, region, node count, K8sGPT version) in the weather response
6. WHEN Result_CRDs cannot be read, THE System SHALL return an error state with diagnostic information
7. THE System SHALL complete weather calculations within 5 seconds

### Requirement 4: Query Classification and Routing

**User Story:** As a DevOps engineer, I want my queries to be intelligently classified, so that the system retrieves the most relevant context for my question.

#### Acceptance Criteria

1. WHEN a User submits a query, THE Query_Router SHALL classify it using deterministic pattern matching
2. THE Query_Router SHALL support categories: pod_issues, deployment_issues, service_issues, resource_issues, argocd_issues, aws_issues, general_k8s, and general_chat
3. WHEN a query matches multiple patterns, THE Query_Router SHALL select the most specific category
4. WHEN a query contains unsafe patterns (code execution, credential access), THE System SHALL reject it with a safety warning
5. THE Query_Router SHALL complete classification within 100 milliseconds
6. THE System SHALL log the classification decision for debugging purposes

### Requirement 5: Context Enrichment from Kubernetes and AWS APIs

**User Story:** As a DevOps engineer, I want the chatbot to automatically gather relevant cluster context, so that I receive accurate and complete answers.

#### Acceptance Criteria

1. WHEN a query is classified, THE Enrichment_Engine SHALL read relevant Result_CRDs from the Target_Cluster
2. WHEN a query is classified as pod_issues, THE Enrichment_Engine SHALL retrieve pod status, events, and logs for mentioned pods
3. WHEN a query is classified as deployment_issues, THE Enrichment_Engine SHALL retrieve deployment status, replica counts, and recent events
4. WHEN a query is classified as argocd_issues, THE Enrichment_Engine SHALL read ArgoCD Application CRDs and sync status
5. WHEN a query is classified as aws_issues, THE Enrichment_Engine SHALL make targeted boto3 calls (EC2 DescribeInstances, ELB DescribeLoadBalancers) using User credentials
6. THE Enrichment_Engine SHALL limit AWS API calls to 3 per query to minimize costs
7. WHEN enrichment fails, THE System SHALL proceed with available context and note the failure in the response
8. THE Enrichment_Engine SHALL complete enrichment within 10 seconds

### Requirement 6: RAG-Powered Knowledge Retrieval

**User Story:** As a DevOps engineer, I want the chatbot to search our team's knowledge base, so that I can benefit from previously documented solutions.

#### Acceptance Criteria

1. WHEN a query is received, THE RAG_Engine SHALL generate embeddings using a small embedding model
2. WHEN embeddings are generated, THE RAG_Engine SHALL perform semantic search against the Knowledge_Base using FAISS
3. THE RAG_Engine SHALL retrieve the top 5 most relevant knowledge base entries with similarity scores above 0.7
4. WHEN relevant entries are found, THE System SHALL include them in the LLM prompt with citations
5. THE RAG_Engine SHALL cache embeddings for 3600 seconds to reduce computation
6. WHEN the Knowledge_Base is empty, THE System SHALL proceed without KB context and note this in the response

### Requirement 7: LLM Response Generation

**User Story:** As a DevOps engineer, I want to receive clear, actionable troubleshooting guidance, so that I can resolve issues quickly.

#### Acceptance Criteria

1. WHEN context is enriched, THE System SHALL render a structured prompt using the Prompt_Template_Engine
2. THE System SHALL include query classification, K8sGPT findings, K8s API data, AWS context, and KB entries in the prompt
3. WHEN the prompt is rendered, THE System SHALL send it to the LLM with a maximum token limit of 4096
4. WHEN the LLM responds, THE System SHALL parse the response and extract recommendations, commands, and warnings
5. THE System SHALL include citations for KB entries used in the response
6. WHEN K8sGPT findings are included, THE System SHALL highlight them prominently in the response
7. THE System SHALL complete response generation within 30 seconds
8. IF the LLM response contains unsafe commands, THEN THE System SHALL add safety warnings

### Requirement 8: Input Validation and Safety

**User Story:** As a system administrator, I want all user inputs to be validated and sanitized, so that the system remains secure and stable.

#### Acceptance Criteria

1. WHEN a User submits a query, THE System SHALL validate it is between 1 and 2000 characters
2. WHEN a query contains SQL injection patterns, THE System SHALL reject it with an error message
3. WHEN a query contains shell command injection patterns, THE System SHALL reject it with an error message
4. WHEN a query contains attempts to access credentials or secrets, THE System SHALL reject it with a security warning
5. THE System SHALL sanitize all user inputs before logging or storing them
6. WHEN AWS credentials are submitted, THE System SHALL validate they match expected formats before attempting authentication

### Requirement 9: Rate Limiting and Cost Control

**User Story:** As a system administrator, I want to control API usage and costs, so that the system remains economically viable.

#### Acceptance Criteria

1. THE System SHALL limit each User to 20 queries per minute
2. WHEN a User exceeds the rate limit, THE System SHALL return a 429 error with retry-after information
3. THE System SHALL limit AWS API calls to 3 per query
4. THE System SHALL cache cluster discovery results for 300 seconds
5. THE System SHALL cache RAG embeddings for 3600 seconds
6. THE System SHALL use small LLM models (GPT-3.5-turbo or equivalent) for cost efficiency
7. THE System SHALL limit LLM context windows to 4096 tokens

### Requirement 10: Conversation History Management

**User Story:** As a DevOps engineer, I want the chatbot to remember our conversation context, so that I can ask follow-up questions naturally.

#### Acceptance Criteria

1. WHEN a User submits a query, THE System SHALL retrieve the last 5 messages from their conversation history
2. WHEN a response is generated, THE System SHALL store the query and response in conversation history
3. THE System SHALL maintain separate conversation histories for each User
4. THE System SHALL limit conversation history to 50 messages per User
5. WHEN a User's session ends, THE System SHALL persist their conversation history for 24 hours
6. WHEN a User starts a new session, THE System SHALL load their previous conversation history if available

### Requirement 11: Knowledge Base Management

**User Story:** As a DevOps engineer, I want to submit solutions to the knowledge base, so that the team can benefit from resolved issues.

#### Acceptance Criteria

1. WHEN a User submits a solution, THE System SHALL validate it contains a title, description, and tags
2. WHEN a solution is validated, THE System SHALL generate embeddings and store it in the Knowledge_Base
3. THE System SHALL update the FAISS index immediately after adding a solution
4. WHEN a solution is added, THE System SHALL make it available for retrieval in subsequent queries
5. THE System SHALL store solutions in the shared PVC accessible across all User sessions
6. THE System SHALL support solution updates and deletions by authorized Users

### Requirement 12: K8sGPT Result Integration

**User Story:** As a DevOps engineer, I want K8sGPT diagnostic results integrated into chat responses, so that I have comprehensive cluster insights.

#### Acceptance Criteria

1. WHEN generating a response, THE System SHALL read Result_CRDs from the Target_Cluster
2. WHEN Result_CRDs are found, THE System SHALL filter them by relevance to the User's query
3. THE System SHALL include relevant Result_CRD findings in the LLM prompt
4. WHEN Result_CRDs contain critical issues, THE System SHALL highlight them prominently in the response
5. THE System SHALL include Result_CRD metadata (analyzer name, severity, timestamp) in responses
6. WHEN no relevant Result_CRDs are found, THE System SHALL proceed without K8sGPT context

### Requirement 13: Multi-Cluster Support

**User Story:** As a DevOps engineer managing multiple clusters, I want to switch between clusters easily, so that I can troubleshoot across my infrastructure.

#### Acceptance Criteria

1. WHEN a User selects a different Target_Cluster, THE System SHALL generate a new Bearer_Token for that cluster
2. WHEN the Target_Cluster changes, THE System SHALL update the Kubernetes API client configuration
3. THE System SHALL maintain separate conversation histories for each Target_Cluster
4. WHEN switching clusters, THE System SHALL clear cached cluster-specific data
5. THE System SHALL display the current Target_Cluster name prominently in the UI
6. THE System SHALL complete cluster switching within 3 seconds

### Requirement 14: Frontend User Interface

**User Story:** As a DevOps engineer, I want an intuitive interface for authentication, cluster selection, and chat, so that I can work efficiently.

#### Acceptance Criteria

1. WHEN the application loads, THE System SHALL display a login form for Kion credentials
2. WHEN authenticated, THE System SHALL display a cluster selector dropdown with discovered clusters
3. WHEN a cluster is selected, THE System SHALL display the weather widget, chat interface, and results panel
4. THE System SHALL update the weather widget every 60 seconds automatically
5. WHEN credentials are expiring, THE System SHALL display a countdown badge with time remaining
6. THE System SHALL display K8sGPT Result_CRDs in a dedicated results panel with severity indicators
7. THE System SHALL provide a solution submission dialog accessible from chat responses

### Requirement 15: Deployment and Infrastructure

**User Story:** As a platform engineer, I want the system deployed with proper separation of concerns, so that it is maintainable and scalable.

#### Acceptance Criteria

1. THE Operator SHALL be deployed per monitored cluster using ArgoCD
2. THE System (frontend + backend) SHALL be deployed once in a common cluster
3. THE System SHALL use a shared PVC for the Knowledge_Base accessible to all backend pods
4. THE System SHALL expose an ingress endpoint with TLS termination
5. THE Operator SHALL create Result_CRDs in its local cluster namespace
6. THE System SHALL read Result_CRDs from remote clusters using per-User Bearer_Tokens
7. THE System SHALL support horizontal scaling of backend pods without state conflicts

### Requirement 16: Startup Validation and Health Checks

**User Story:** As a platform engineer, I want the system to validate its configuration on startup, so that misconfigurations are caught early.

#### Acceptance Criteria

1. WHEN the backend starts, THE System SHALL validate that required environment variables are set
2. WHEN the backend starts, THE System SHALL verify the Knowledge_Base PVC is mounted and writable
3. WHEN the backend starts, THE System SHALL load prompt templates and validate their structure
4. WHEN the backend starts, THE System SHALL initialize the FAISS index or create it if missing
5. IF startup validation fails, THEN THE System SHALL log detailed error messages and exit with a non-zero code
6. THE System SHALL expose /health and /ready endpoints for Kubernetes probes
7. THE /ready endpoint SHALL return 200 only after successful startup validation

### Requirement 17: Error Handling and Observability

**User Story:** As a platform engineer, I want comprehensive error handling and logging, so that I can diagnose and resolve issues quickly.

#### Acceptance Criteria

1. WHEN any component encounters an error, THE System SHALL log it with severity, timestamp, User ID, and stack trace
2. WHEN a User query fails, THE System SHALL return a user-friendly error message without exposing internal details
3. THE System SHALL log all AWS API calls with duration and response status
4. THE System SHALL log all LLM API calls with token counts and latency
5. THE System SHALL expose Prometheus metrics for query latency, error rates, and API call counts
6. WHEN the Credential_Store is full, THE System SHALL evict the oldest expired credentials
7. THE System SHALL handle Kubernetes API connection failures gracefully and retry with exponential backoff
