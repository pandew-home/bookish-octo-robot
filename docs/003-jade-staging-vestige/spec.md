# Feature Specification: JADE Staging Vestige Deploy (002 Integration)

**Feature Branch**: `003-jade-staging-vestige`  
**Created**: 2026-07-26  
**Status**: Draft  

**Input**: Integrate the completed GitHub feature branch `002-vestige-memory-mcp` into JADE GitLab deployments for testing on `jadeuc-staging-b` (cluster jade-2pst-b). Snapshot current staging to `jadeuc-faiss` for FAISS-era rollback, then replace `jadeuc-staging-b` with Vestige-capable deploy configuration. Full `MEMORY_BACKEND=vestige` on first rollout with PVC growth for model cache. Operator repo out of scope unless smoke fails.

**Related**: `specs/002-vestige-memory-mcp/` (product behavior already specified/implemented on GitHub). This feature is the **delivery cutover** into JADE staging, not a redesign of memory or kube policy semantics.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe FAISS rollback snapshot (Priority: P1)

A platform engineer freezes today’s working FAISS-era staging deploy on a dedicated branch before any Vestige cutover, so staging can return to a known-good state if the new rollout fails.

**Why this priority**: Without a snapshot, replacing `jadeuc-staging-b` loses the only tested JADE staging configuration.

**Independent Test**: Create `jadeuc-faiss` from pre-cutover `jadeuc-staging-b`; verify branch tip matches the pre-cutover commit and documents the pinned image tag.

**Acceptance Scenarios**:

1. **Given** `jadeuc-staging-b` at a known FAISS-era tip, **When** the engineer creates `jadeuc-faiss`, **Then** that branch points at the same commit (or an explicit snapshot commit) and is pushed to GitLab.
2. **Given** `jadeuc-faiss` exists, **When** cutover of `jadeuc-staging-b` proceeds, **Then** `jadeuc-faiss` remains unchanged as the rollback source.
3. **Given** a failed Vestige rollout, **When** the engineer follows the documented rollback path, **Then** staging can be restored using `jadeuc-faiss` (image pin and/or branch retarget) without reconstructing FAISS config from memory.

---

### User Story 2 - Staging runs Vestige-capable chatbot image (Priority: P1)

A tester on jade-2pst-b reaches `k8s-assistant.staging.jadeuc.com` and uses the chatbot built from the 002 product line: colocated institutional memory (Vestige), no Save-to-KB UI, session-based live Kubernetes tools, and observe-default mutation policy.

**Why this priority**: This is the primary value of the cutover—staging must exercise the real 002 runtime, not only chart YAML.

**Independent Test**: After deploy, open staging URL; confirm health endpoints succeed, login + cluster select works, chat returns answers, and UI has no Save-to-KB flow.

**Acceptance Scenarios**:

1. **Given** GitLab `main` has produced a Vestige-capable image, **When** `jadeuc-staging-b` pins that image and Argo syncs, **Then** the chatbot pod becomes Ready and serves `/api/health` and `/api/health/ready`.
2. **Given** the new image is running, **When** a user authenticates and selects a cluster, **Then** they can complete a troubleshooting chat turn without FAISS/KB seeding errors.
3. **Given** the new UI is loaded, **When** the user inspects the main chat experience, **Then** there is no “Save to knowledge base” control.
4. **Given** Vestige is configured on, **When** the pod starts with sufficient PVC space, **Then** memory data paths under the shared data volume are used for institutional memory (not the retired FAISS index path as the chat memory backend).

---

### User Story 3 - Vestige memory on with durable storage (Priority: P1)

Staging runs with institutional memory enabled (`vestige`), backed by grown persistent storage so embedding/model cache and memory DB can persist across pod restarts on the single-replica RWO volume.

**Why this priority**: User-selected full Vestige posture for first staging rollout; memory without PVC capacity will OOM or fail model download.

**Independent Test**: Confirm env shows vestige backend; PVC size increased vs pre-cutover; after first successful memory use, data remains under the vestige data directory after pod recreate (same PVC).

**Acceptance Scenarios**:

1. **Given** staging deploy values, **When** the pod starts, **Then** memory backend is vestige (not noop) for the primary path.
2. **Given** the staging PVC overlay, **When** compared to pre-cutover capacity, **Then** storage is enlarged enough for vestige DB + model cache (explicit size documented in deploy values).
3. **Given** Vestige is temporarily unavailable inside the pod, **When** the user chats, **Then** chat still succeeds with a non-blocking degraded-memory indication (behavior inherited from 002).
4. **Given** a Recreate rollout on RWO, **When** a new pod starts, **Then** prior vestige data on the PVC remains available (no requirement for multi-replica RWX in this feature).

---

### User Story 4 - Observe-default security posture on staging (Priority: P2)

Staging matches constitution observe-default: mutating execution gated by policy defaults (mutate off), pod ServiceAccount limited to reading K8sGPT Results, live diagnostics use the user’s session credentials.

**Why this priority**: JADE staging must not regress to a broad cluster-admin SA while adopting 002.

**Independent Test**: Review deployed RBAC and env policy flags; confirm SA cannot broadly list secrets; live pod listing still works via user session after auth.

**Acceptance Scenarios**:

1. **Given** staging chart/env defaults, **When** kube API wrapper policy is inspected, **Then** mutate is disabled by default and free-text recommendations remain allowed.
2. **Given** the chatbot pod ServiceAccount, **When** its ClusterRole is inspected, **Then** it is limited to K8sGPT Result read access (not broad secret/pod cluster read).
3. **Given** a valid user session with cluster credentials, **When** the user asks about live pods, **Then** diagnostics can still proceed via session clients (not the pod SA’s broad privileges).

---

### Edge Cases

- JADE CI cannot download Vestige binaries from the public internet during image build.
- First Vestige start downloads embedding models and exceeds memory/CPU limits or PVC free space.
- Image built from GitLab `main` but staging still pins an old FAISS tag (config/image skew).
- PVC expansion blocked by storage class; need delete/recreate (data loss) vs expand in place.
- After SA tighten, weather/K8sGPT Results disappear because Results live in another namespace without binding.
- Rollback to `jadeuc-faiss` while PVC already contains vestige data (harmless leftover dirs).
- UID mismatch between image user and chart securityContext breaks PVC write for vestige.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create and publish a GitLab branch `jadeuc-faiss` from the pre-cutover `jadeuc-staging-b` tip before modifying staging for Vestige.
- **FR-002**: System MUST land 002 product behavior on GitLab `main` such that the compliance docker pipeline produces a chatbot image that includes colocated Vestige memory capability and excludes FAISS as the chat memory backend.
- **FR-003**: System MUST replace `jadeuc-staging-b` deploy configuration so it pins a Vestige-capable image and configures memory backend vestige with loopback Vestige URL and data directories on the chatbot PVC.
- **FR-004**: System MUST grow (or document and apply equivalent) staging PVC capacity to accommodate vestige database and model cache beyond the pre-cutover FAISS footprint.
- **FR-005**: System MUST restore health probes to application health endpoints that the Vestige-capable image serves (not root-path workarounds required only for older images).
- **FR-006**: System MUST remove FAISS/KB seeding configuration from the staging deploy path (no reliance on Save-to-KB or KB seeder for chat).
- **FR-007**: System MUST apply observe-default kube API policy defaults on staging (mutate off unless an explicit reviewed overlay enables it).
- **FR-008**: System MUST tighten the chatbot pod ServiceAccount RBAC on staging to K8sGPT Results read-only for cluster-scoped access granted to that SA.
- **FR-009**: System MUST preserve JADE staging environment concerns: ingress host, TLS issuer, registry pull secrets, Vault-sourced LLM credentials, single-replica Recreate strategy, and disabled ResourceQuota/PDB where required by platform policy.
- **FR-010**: System MUST document rollback using `jadeuc-faiss` and the pre-cutover image tag.
- **FR-011**: System MUST NOT change `bookish-octo-robot-operator` as part of the happy path; operator changes are allowed only if staging smoke proves Results access is broken after SA tighten.
- **FR-012**: System MUST keep institutional memory cluster-scoped (shared findings), consistent with 002—not per-user private memory.

### Key Entities

- **Deploy branch snapshot (`jadeuc-faiss`)**: Immutable-enough rollback branch of FAISS-era staging overlays and image pin.
- **Image build line (GitLab `main`)**: Source of truth for container contents (app + Vestige runtime).
- **Staging deploy line (`jadeuc-staging-b`)**: Chart + cluster overlay + RBAC that Argo applies to jade-2pst-b.
- **Staging PVC**: Durable volume holding conversations and vestige data/model-cache.
- **Pod ServiceAccount binding**: Least-privilege Results reader for host-cluster CRDs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `jadeuc-faiss` exists on GitLab and matches the pre-cutover staging commit used for snapshot (verifiable by commit SHA).
- **SC-002**: Within one staging cutover session, a tester can authenticate, select a cluster, and complete at least one successful chat turn on the public staging URL.
- **SC-003**: Staging pod reports Ready and health endpoints succeed without root-path probe overrides.
- **SC-004**: Deploy configuration shows vestige memory enabled; FAISS/KB seeder settings are absent from the active staging env.
- **SC-005**: Staging PVC size is larger than the pre-cutover FAISS-era size (or expand procedure completed and recorded).
- **SC-006**: Rollback procedure is documented and can be executed by retargeting deploy to `jadeuc-faiss` / prior image pin without needing the original author.
- **SC-007**: Pod ServiceAccount cluster permissions do not include broad Secret data access; Results read remains available or a documented operator follow-up is opened within the same test window.

## Assumptions

- GitHub `002-vestige-memory-mcp` (at or after commit `21bb2a53`) is the product reference for behavior and file-level porting.
- GitLab JADE layout remains: **`main` builds images**; **`jadeuc-*` deploys** via compliance framework + Argo (no committed `argocd/` tree in app repo).
- Staging cluster is jade-2pst-b; ingress remains `k8s-assistant.staging.jadeuc.com`.
- LLM secrets continue via Vault Static Secret / existing path; no secrets committed to git.
- Single replica + RWO PVC remains acceptable for staging (Recreate strategy).
- Operator stack (K8sGPT Results) already runs from `bookish-octo-robot-operator` `jadeuc-staging-b`.
- Network/policy for build agents may require vendoring Vestige binaries; plan will resolve supply chain without changing product semantics.
- Production JADE clusters and GitHub `main` merge of 002 are out of scope for this feature’s acceptance (GitLab main is the required image line).

## Out of Scope

- Production or additional JADE clusters beyond jade-2pst-b staging.
- Multi-user history isolation / IDOR hardening.
- Redesign of Vestige protocols or kube_policy semantics (owned by 002).
- Operator observability chart changes unless smoke forces them.
- Changing Ravix/Vault LLM credential paths.
