# Feature Specification: JADE Staging Vestige Deploy (002 Integration)

**Feature Branch**: `003-jade-staging-vestige`  
**Created**: 2026-07-26  
**Status**: Ready for implementation  
**Last updated**: 2026-07-26 (clarifications integrated; internal consistency pass)

**Input**: Integrate the completed GitHub feature branch `002-vestige-memory-mcp` into JADE GitLab deployments for testing on `jadeuc-staging-b` (overlay cluster key **jade-2pst-b**; EKS name **jade-2pst-b-rgp**). Snapshot current staging to `jadeuc-faiss` for FAISS-era rollback, then replace `jadeuc-staging-b` with Vestige-capable deploy configuration. Full `MEMORY_BACKEND=vestige` on first rollout. PVC **≥10Gi** (keep existing size if already large enough). Preserve conversation history on the shared volume. Operator repo out of scope unless smoke fails.

**Related**: `specs/002-vestige-memory-mcp/` (product behavior already specified/implemented on GitHub). This feature is the **delivery cutover** into JADE staging, not a redesign of memory or kube policy semantics.

## Cluster naming (canonical)

| Term | Meaning |
|------|---------|
| **jade-2pst-b** | Git overlay path key (`clusters/jade-2pst-b/`) and short cluster id in docs |
| **jade-2pst-b-rgp** | EKS / platform cluster name for the same staging environment |
| **bookish-octo-robot** | Application namespace on that cluster |

Use **jade-2pst-b** for paths and overlays; use **jade-2pst-b-rgp** only when referring to the EKS cluster resource name.

## Clarifications

### Session 2026-07-26

- Q: How should the first GitLab `main` image build obtain the Vestige binary? → A: **Vendor first** — commit/copy binaries under `third_party/vestige` (or internal mirror) before first package; no public GitHub download in Dockerfile for the happy path.
- Q: What PVC capacity is required for staging Vestige? → A: **≥10Gi** is sufficient (small Vestige DB). **Do not require 40Gi.** Keep existing PVC if already ≥10Gi; only grow if below 10Gi.
- Q: When Vestige cutover fails, which rollback path is primary? → A: **Image re-pin on `jadeuc-staging-b`** (pre-cutover FAISS `image.tag` from snapshot notes) is primary; Argo/branch retarget to `jadeuc-faiss` is secondary.
- Q: Must existing staging conversation history on the PVC survive the Vestige cutover? → A: **Preserve** `/data/conversations` across deploy; no intentional wipe; avoid PVC recreate that would destroy history.
- Q: Where must the memory + kube_policy pytest gate run before GitLab `main` merge? → A: **Local or any runner OK** — green pytest attached to MR/task log is enough; GitLab CI pytest job optional.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe FAISS rollback snapshot (Priority: P1) — FR-001, FR-010, SC-001, SC-006

A platform engineer freezes today’s working FAISS-era staging deploy on a dedicated branch before any Vestige cutover, so staging can return to a known-good state if the new rollout fails.

**Why this priority**: Without a snapshot, replacing `jadeuc-staging-b` loses the only tested JADE staging configuration and the pre-cutover image pin needed for primary rollback.

**Independent Test**: Create `jadeuc-faiss` from pre-cutover `jadeuc-staging-b`; verify branch tip matches the pre-cutover commit and documents the pinned image tag.

**Acceptance Scenarios**:

1. **Given** `jadeuc-staging-b` at a known FAISS-era tip, **When** the engineer creates `jadeuc-faiss`, **Then** that branch points at the same commit (or an explicit snapshot commit) and is pushed to GitLab.
2. **Given** `jadeuc-faiss` exists, **When** cutover of `jadeuc-staging-b` proceeds, **Then** `jadeuc-faiss` remains unchanged as the rollback source of truth for FAISS-era values.
3. **Given** a failed Vestige rollout, **When** the engineer follows the documented rollback path, **Then** staging is restored first by **re-pinning the pre-cutover FAISS image tag on `jadeuc-staging-b`**; branch/Argo retarget to `jadeuc-faiss` remains secondary if image re-pin is insufficient.

---

### User Story 2 - Staging runs Vestige-capable chatbot image (Priority: P1) — FR-002, FR-003, FR-005, FR-006, SC-002, SC-003, SC-004

A tester on jade-2pst-b reaches `k8s-assistant.staging.jadeuc.com` and uses the chatbot built from the 002 product line: colocated institutional memory (Vestige), no Save-to-KB UI, session-based live Kubernetes tools, and observe-default mutation policy.

**Why this priority**: This is the primary value of the cutover—staging must exercise the real 002 runtime, not only chart YAML.

**Independent Test**: After deploy, open staging URL; confirm health endpoints succeed, login + cluster select works, chat returns answers, and UI has no Save-to-KB flow.

**Acceptance Scenarios**:

1. **Given** GitLab `main` has produced a Vestige-capable image (vendored Vestige binary; pytest green recorded), **When** `jadeuc-staging-b` pins that image and Argo syncs, **Then** the chatbot pod becomes Ready and serves `/api/health` and `/api/health/ready`.
2. **Given** the new image is running, **When** a user authenticates and selects a cluster, **Then** they can complete a troubleshooting chat turn without FAISS/KB seeding errors.
3. **Given** the new UI is loaded, **When** the user inspects the main chat experience, **Then** there is no “Save to knowledge base” control.
4. **Given** Vestige is configured on, **When** the pod starts with PVC ≥10Gi, **Then** memory data paths under the shared data volume are used for institutional memory (not the retired FAISS index path as the chat memory backend).

---

### User Story 3 - Vestige memory on with durable storage (Priority: P1) — FR-003, FR-004, FR-012, FR-013, SC-004, SC-005, SC-010

Staging runs with institutional memory enabled (`vestige`), backed by the existing single-replica RWO PVC (or a volume ≥**10Gi**) so vestige data can persist across pod restarts. Conversation history on the volume is preserved.

**Why this priority**: Full Vestige posture for first staging rollout without oversized PVC requirements; history continuity for testers.

**Independent Test**: Confirm env shows vestige backend; PVC size is ≥10Gi (grow only if currently below 10Gi); after first successful memory use, data remains under the vestige data directory after pod Recreate (same PVC); pre-cutover conversations still present.

**Acceptance Scenarios**:

1. **Given** staging deploy values, **When** the pod starts, **Then** memory backend is vestige (not noop) for the primary path.
2. **Given** the staging PVC, **When** capacity is checked, **Then** size is at least **10Gi**; if pre-cutover size is already ≥10Gi, retaining that size is acceptable (no mandatory grow to 40Gi or any larger target).
3. **Given** Vestige is temporarily unavailable inside the pod, **When** the user chats, **Then** chat still succeeds with a non-blocking degraded-memory indication (behavior inherited from 002; verify via unit tests and/or staging smoke note).
4. **Given** a Recreate rollout on RWO (same PVC), **When** a new pod starts, **Then** prior vestige data on the PVC remains available (no multi-replica RWX required).
5. **Given** institutional memory is in use, **When** two sessions contribute findings, **Then** memory remains cluster-scoped (shared), not per-user private (FR-012).
6. **Given** pre-cutover conversation files under `/data/conversations`, **When** Vestige cutover completes, **Then** those conversations remain available (no intentional wipe; no default PVC recreate).

---

### User Story 4 - Observe-default security posture on staging (Priority: P1) — FR-007, FR-008, SC-007, SC-009

Staging matches constitution observe-default: mutating execution gated by policy defaults (mutate off), pod ServiceAccount limited to reading K8sGPT Results, live diagnostics use the user’s session credentials. **This story is part of MVP acceptance** (not deferred hardening).

**Why this priority**: JADE staging must not regress to a broad cluster-admin SA while adopting 002.

**Independent Test**: Review deployed RBAC and env policy flags; confirm SA cannot broadly list secrets; live pod listing still works via user session after auth; free-text recommendations still appear when mutate is off.

**Acceptance Scenarios**:

1. **Given** staging chart/env defaults, **When** kube API wrapper policy is inspected, **Then** mutate is disabled by default and free-text recommendations remain allowed.
2. **Given** the chatbot pod ServiceAccount, **When** its ClusterRole is inspected, **Then** it is limited to K8sGPT Result read access (not broad secret/pod cluster read).
3. **Given** a valid user session with cluster credentials, **When** the user asks about live pods, **Then** diagnostics can still proceed via session clients (not the pod SA’s broad privileges).

---

### Edge Cases

- JADE CI cannot reach public GitHub for Vestige binaries — mitigated by **vendor-first** supply chain (no public curl in Dockerfile happy path).
- First Vestige start downloads embedding models and exceeds memory/CPU limits or free space on a small PVC.
- Image built from GitLab `main` but staging still pins an old FAISS tag (config/image skew).
- PVC below **10Gi** and cannot grow — document and resolve before cutover is done (do not wipe conversations as default).
- After SA tighten, weather/K8sGPT Results disappear because Results live in another namespace without binding → operator follow-up only if smoke proves it (FR-011).
- Rollback via image re-pin while PVC already contains vestige data (harmless leftover dirs under `/data/vestige`).
- UID mismatch between image user and chart securityContext breaks PVC write for vestige.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Delivery process MUST create and publish a GitLab branch `jadeuc-faiss` from the pre-cutover `jadeuc-staging-b` tip before modifying staging for Vestige.
- **FR-002**: Delivery process MUST land 002 product behavior on GitLab `main` such that the compliance docker pipeline produces a chatbot image that includes colocated Vestige memory capability and excludes FAISS as the chat memory backend. Vestige binaries MUST be **vendored** into the build context (e.g. `third_party/vestige/` or internal mirror COPY)—**not** downloaded from public GitHub in the Dockerfile happy path. Automated unit/contract tests for memory and kube_policy against the ported tree MUST be green before merge; they MAY run **locally or on any runner** with green output attached to the MR or task log (GitLab CI pytest job optional).
- **FR-003**: Delivery process MUST replace `jadeuc-staging-b` deploy configuration so it pins a Vestige-capable image and configures memory backend vestige with loopback Vestige URL and data directories on the chatbot PVC. (Related: FR-006 removes KB path.)
- **FR-004**: Delivery process MUST ensure staging PVC capacity is at least **10Gi**. If pre-cutover PVC is already ≥10Gi, retaining current size is acceptable. **40Gi (or any larger mandatory growth) is not required.** If capacity is below 10Gi and cannot be raised without destroying conversations, process MUST stop and document a path that preserves FR-013 before cutover is done.
- **FR-005**: Delivery process MUST restore health probes to application health endpoints that the Vestige-capable image serves (not root-path workarounds required only for older images).
- **FR-006**: Delivery process MUST remove FAISS/KB seeding configuration from the staging deploy path (no reliance on Save-to-KB or KB seeder for chat). Complements FR-003 memory enablement.
- **FR-007**: Delivery process MUST apply observe-default kube API policy defaults on staging (mutate off unless an explicit reviewed overlay enables it) and MUST keep free-text remediation recommendations allowed when mutate is off.
- **FR-008**: Delivery process MUST tighten the chatbot pod ServiceAccount RBAC on staging to K8sGPT Results read-only for cluster-scoped access granted to that SA **before** the first Vestige Argo sync is treated as successful cutover (same deploy push as chart/env changes).
- **FR-009**: Delivery process MUST preserve JADE staging environment concerns: ingress host, TLS issuer, registry pull secrets, Vault-sourced LLM credentials, single-replica Recreate strategy, and disabled ResourceQuota/PDB where required by platform policy.
- **FR-010**: Delivery process MUST document rollback. **Primary path**: re-pin FAISS-era `image.tag` on `jadeuc-staging-b` and push (values from pre-cutover notes / `jadeuc-faiss`). **Secondary path**: Argo/branch retarget to `jadeuc-faiss`.
- **FR-011**: Delivery process MUST NOT change `bookish-octo-robot-operator` as part of the happy path; operator changes are allowed only if staging smoke proves Results access is broken after SA tighten.
- **FR-012**: Delivery process MUST keep institutional memory cluster-scoped (shared findings), consistent with 002—not per-user private memory (verify via port fidelity and smoke note).
- **FR-013**: Delivery process MUST **preserve** existing staging conversation history under `/data/conversations` on the shared data volume; MUST NOT intentionally wipe it as part of the Vestige cutover.

### Key Entities

- **Deploy branch snapshot (`jadeuc-faiss`)**: Frozen FAISS-era staging overlays and image pin for secondary rollback and value recovery.
- **Image build line (GitLab `main`)**: Source of truth for container contents (app + vendored Vestige runtime).
- **Staging deploy line (`jadeuc-staging-b`)**: Chart + cluster overlay + RBAC that Argo applies to jade-2pst-b (EKS: jade-2pst-b-rgp).
- **Staging PVC**: Durable volume holding conversations, vestige data, and optional model-cache; size ≥10Gi; conversations preserved across cutover.
- **Pod ServiceAccount binding**: Least-privilege Results reader for host-cluster CRDs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `jadeuc-faiss` exists on GitLab and matches the pre-cutover staging commit used for snapshot (verifiable by commit SHA).
- **SC-002**: Within one staging cutover session, a tester can authenticate, select a cluster, and complete at least one successful chat turn on the public staging URL.
- **SC-003**: Staging pod reports Ready and health endpoints succeed without root-path probe overrides.
- **SC-004**: Deploy configuration shows vestige memory enabled; FAISS/KB seeder settings are absent from the active staging env.
- **SC-005**: Staging PVC size is **≥10Gi** (recorded in deploy values or confirmed live). Keep-as-is satisfies this if already ≥10Gi. No requirement to grow to 40Gi.
- **SC-006**: Rollback procedure is documented with **image re-pin on `jadeuc-staging-b` first**, then secondary branch/Argo retarget to `jadeuc-faiss`; a second engineer can execute without the original author.
- **SC-007**: Pod ServiceAccount cluster permissions do not include broad Secret data access; Results read remains available or a documented operator follow-up is opened within the same test window. **Required for MVP acceptance.**
- **SC-008**: Before GitLab `main` merge, pytest covering memory + kube_policy defaults is green when run **locally or on any runner**, and the green result is recorded in the MR or task log (GitLab CI pytest job not required).
- **SC-009**: Staging smoke or test evidence notes: (a) free-text recommendations still allowed with mutate off; (b) degraded-memory path covered by unit tests and/or a manual note; (c) memory scope is cluster-shared per 002.
- **SC-010**: Pre-cutover conversation data under `/data/conversations` remains present after cutover (spot-check files or API history as available).

## Assumptions

- GitHub `002-vestige-memory-mcp` (at or after commit `21bb2a53`) is the product reference for behavior and file-level porting.
- GitLab JADE layout remains: **`main` builds images**; **`jadeuc-*` deploys** via compliance framework + Argo (no committed `argocd/` tree in app repo).
- Staging overlay key is jade-2pst-b; EKS name jade-2pst-b-rgp; ingress remains `k8s-assistant.staging.jadeuc.com`.
- LLM secrets continue via Vault Static Secret / existing path; no secrets committed to git.
- Single replica + RWO PVC remains acceptable for staging (Recreate strategy on the **same** volume).
- Operator stack (K8sGPT Results) already runs from `bookish-octo-robot-operator` `jadeuc-staging-b`.
- Vestige binary supply for JADE is **vendor-first** (`third_party/vestige/` or internal mirror); public GitHub curl is not the happy path.
- Staging Vestige DB is small; **10Gi** PVC floor is enough; large model-cache sizing is not a cutover requirement.
- Production JADE clusters and GitHub `main` merge of 002 are out of scope for this feature’s acceptance (GitLab main is the required image line).

## Out of Scope

- Production or additional JADE clusters beyond jade-2pst-b staging.
- Multi-user history isolation / IDOR hardening.
- Redesign of Vestige protocols or kube_policy semantics (owned by 002).
- Operator observability chart changes unless smoke forces them.
- Changing Ravix/Vault LLM credential paths.
- Mandatory PVC growth to 40Gi (or any size above the **10Gi** floor when already satisfied).
- Public GitHub download of Vestige binaries in the Dockerfile happy path.
- Intentional wipe of staging conversation history as part of cutover.
