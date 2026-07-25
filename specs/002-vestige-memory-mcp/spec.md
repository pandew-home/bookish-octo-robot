# Feature Specification: Vestige Memory + Code-Enforced Cluster Access

**Feature Branch**: `002-vestige-memory-mcp`  
**Created**: 2026-07-25  
**Updated**: 2026-07-25  
**Status**: Draft  

**Input**:

1. Move the chatbot from FAISS-based vector KB to a better local memory tool (Vestige-class MCP), auto-save troubleshooting steps, auto-recall relevant answers, data local to the cluster; remove Save-to-KB UI and FAISS save/retrieve.  
2. Remove prompting guards that try to stop recommendations or control cluster safety in the system prompt—except that the assistant must only use the approved Python Kubernetes API wrappers for cluster access. Real permissions come from (a) the authenticated user credentials and (b) explicit allow/deny flags on those Python kube API wrappers. Goal: stop fighting the model over recommendations; free-text advice is allowed; actual cluster changes only occur when wrappers and user credentials permit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic recall during troubleshooting (Priority: P1)

An engineer authenticates, selects a cluster, and asks the chatbot about a live problem. Without a separate knowledge-base UI, the assistant retrieves relevant prior troubleshooting memories from cluster-local memory and uses them with live cluster evidence.

**Why this priority**: Core value of replacing FAISS with automatic institutional memory.

**Independent Test**: Seed memory with a known solution for failure mode A; ask about A; reply reflects prior lesson without save/search UI.

**Acceptance Scenarios**:

1. **Given** healthy memory with a prior solution for issue type A, **When** the user asks about A, **Then** the assistant includes relevant prior guidance without a separate KB search step.
2. **Given** no relevant memory, **When** the user asks a novel question, **Then** the assistant still answers from live cluster state and does not fail solely because memory is empty.
3. **Given** memory is temporarily unavailable, **When** the user chats, **Then** they still get a live-cluster-grounded answer with non-blocking degraded-memory indication.

---

### User Story 2 - Automatic save of troubleshooting steps (Priority: P1)

After a successful troubleshooting exchange, the system automatically persists durable steps, diagnoses, remediations, and outcomes into cluster-local memory without “Save to knowledge base.”

**Why this priority**: Explicit product goal; removes manual save friction.

**Independent Test**: Complete a durable fix conversation; new session on related question recovers the earlier steps with no save UI used.

**Acceptance Scenarios**:

1. **Given** a successful turn with durable content, **When** the turn completes, **Then** content is stored without manual save.
2. **Given** two nearly identical solutions over time, **When** the second is stored, **Then** memory does not blindly create confusing duplicates (merge/supersede/dedupe acceptable).
3. **Given** ephemeral noise (greetings, pure auth failures), **When** the turn ends, **Then** low-value entries are not stored.

---

### User Story 3 - Free recommendations; hard enforcement only on real cluster actions (Priority: P1)

An engineer receives clear remediation **recommendations** in chat without the product fighting the model via prompt rules that ban or heavily gate “making recommendations.” The assistant may freely suggest kubectl-style steps, YAML changes, or operational advice as text. **Actual** cluster mutations only succeed when (1) the user’s credentials allow them in the cluster and (2) the Python Kubernetes API wrapper flags allow mutating methods. Prompt text no longer tries to double as an authorization system.

**Why this priority**: Operators report constant friction from prompt guards that try to suppress recommendations; safety must live in credentials + wrapper flags, not in arguing with the model.

**Independent Test**:

- Ask for a fix that implies a mutation; confirm the response may include concrete remediation advice without requiring multi-step “approve” phrases **in the prompt contract**.
- With mutate flags **off**, confirm a tool call that would mutate is blocked in code and no change occurs, even if the model “wants” to.
- With mutate flags **on** but user credentials lacking RBAC, confirm the API error surfaces and no elevated access is invented.

**Acceptance Scenarios**:

1. **Given** a diagnosed failing Deployment, **When** the user asks how to fix it, **Then** the assistant may provide direct remediation recommendations in natural language without prompt-enforced refusal to recommend.
2. **Given** wrapper mutate flags are disabled, **When** the agent attempts a mutating cluster operation through tools, **Then** the operation is rejected by the wrapper layer and the cluster state is unchanged.
3. **Given** mutate flags are enabled and the user asks for an action the credentials cannot perform, **When** the wrapper executes, **Then** the failure is the cluster authorization failure (or equivalent), not a prompt-only block.
4. **Given** any cluster access, **When** the assistant needs live cluster data or to act on the cluster, **Then** it uses only the approved Python Kubernetes API wrappers (not ad-hoc shell `kubectl` or bypass clients).

---

### User Story 4 - Remove manual Save-to-KB experience (Priority: P2)

No “Save to knowledge base” UI or required form; manual solution-submit flows for the old vector index are gone.

**Independent Test**: Main chat UI has no Save-to-KB control; normal troubleshooting does not require a manual KB write API.

**Acceptance Scenarios**:

1. **Given** the main authenticated chat screen, **When** a helpful exchange completes, **Then** there is no Save-to-KB button/dialog.
2. **Given** a client still calls a retired manual-save endpoint, **When** called after cutover, **Then** a clear gone/deprecated signal is returned and the old vector store is not written.

---

### User Story 5 - Operators run memory inside the cluster (Priority: P2)

Memory runs as an in-cluster service with durable local volumes; no external SaaS vector DB for core store/recall.

**Independent Test**: Deploy with in-cluster storage only; write via chat; restart pods; recall still works.

**Acceptance Scenarios**:

1. **Given** configured persistent storage, **When** memory starts, **Then** it becomes healthy without a hosted vector SaaS.
2. **Given** chatbot and memory restarts, **When** recalling prior content, **Then** relevant memories remain available.
3. **Given** empty volume on first boot, **When** memory starts, **Then** it initializes cleanly.

---

### Edge Cases

- Memory down/slow: chat degrades to live diagnostics only.
- Conflicting memories: surface conflict rather than equal dual truth when supported.
- Secrets in chat text: scrub/refuse high-risk patterns before memory write.
- Multi-session concurrency: no store corruption under concurrent chats (single-writer topology assumed for memory).
- Cluster switch / single-cluster mode: scope metadata preferred; no credential leakage into memory.
- Model tries shell/kubectl bypass: blocked—only wrapper tools exist for cluster I/O.
- Model recommends a destructive fix in text while mutate flags are off: recommendation text may appear; **execution** does not.
- User credentials expire mid-session: subsequent wrapper calls fail closed.
- Legacy FAISS import optional; missing legacy data does not block go-live.
- First-run embedding/model download: document air-gap bake strategy.

## Requirements *(mandatory)*

### Constitution Constraints *(mandatory for this repo)*

*From `.specify/memory/constitution.md` **v3.0.0** (policy-gated mutation; free recommendations; secrets identify-only):*

- **CC-001**: Cluster **mutations are not authorized by prompt text**. Authorization is **user credentials + Python kube API wrapper policy** (Helm `kubeApi` / env). Dual chat “approve” rituals are **not** the security boundary. Mutate defaults **off**.
- **CC-002**: Live cluster API evidence MUST take precedence over stale K8sGPT Result text **and** recalled memory when they disagree.
- **CC-003**: Secrets MUST NOT appear in git; sessions MUST NOT log credentials; memory MUST NOT store raw secret values; wrappers default to Secret **identify-only** (no data values to the agent).
- **CC-004**: Delivery via Argo CD + Helm; memory in-cluster; no Flux; no secrets in chart git.
- **CC-005**: Production images use git SHA tags when this feature touches deploy/image paths.
- **CC-006**: Public URL changes keep ingress path, apiBaseUrl, publicUrl, and CORS aligned (Save-to-KB removal should not require URL redesign).

### Functional Requirements — Memory (Vestige)

- **FR-001**: System MUST replace FAISS knowledge-base **retrieve** in chat with cluster-local **agent memory** via MCP (store/recall tools—not an in-process vector index in the chatbot).
- **FR-002**: System MUST automatically **recall** relevant memories per troubleshooting turn (or session start) without KB UI.
- **FR-003**: System MUST automatically **persist** durable troubleshooting outcomes without manual “Save to knowledge base.”
- **FR-004**: System MUST remove Save-to-KB / solution-submit UI and discontinue FAISS save/retrieve application paths used for that UX.
- **FR-005**: Memory data MUST persist on cluster volume storage across pod restarts.
- **FR-006**: Day-to-day store/recall MUST NOT require an external commercial vector SaaS; offline-capable after any one-time model bootstrap.
- **FR-007**: Chat MUST remain usable when memory is empty, unavailable, or times out.
- **FR-008**: Recalled memory is **supporting context**, never higher authority than live Kubernetes API observations.
- **FR-009**: Prefer Vestige-class memory (novelty/contradiction/backward retrieval); Vestige is the reference product (spike validated GO).
- **FR-010**: Operators MUST deploy memory via GitOps (Helm/Argo) with non-root posture and resource limits.
- **FR-011**: Document where memory lives, backup, and wipe procedures.
- **FR-012**: Automated tests for recall, auto-save, degraded memory, Save-to-KB removal—without production cluster for unit/contract suite.
- **FR-013**: Decommission FAISS dual-write paths from runtime after cutover.
- **FR-014**: Optional one-time legacy FAISS/solution import MAY exist in a **follow-up**; **out of MVP** for this feature’s tasks. Greenfield Vestige memory is acceptable; missing legacy data MUST NOT block go-live.

### Functional Requirements — Access model (code-enforced)

- **FR-015**: System MUST remove system-prompt rules whose purpose is to **stop the model from recommending remediations** or to simulate authorization via multi-step verbal approval rituals.
- **FR-016**: System prompt (or equivalent agent instructions) MUST retain only minimal cluster-access guidance: **use only the approved Python Kubernetes API wrappers** for all live cluster read/write tool operations (no shelling out to kubectl or alternate clients for those operations).
- **FR-017**: Whether a mutating cluster operation **executes** MUST be determined by **(1)** the authenticated user’s credentials against the cluster API and **(2)** explicit allow/deny (or equivalent) flags on the Python kube API wrapper layer—not by parsing approval phrases in chat as the primary gate.
- **FR-018**: Default product configuration MUST keep mutating wrapper flags **disabled** (safe default) unless operators explicitly enable them for an environment.
- **FR-019**: When a mutation is denied by wrapper flags, the system MUST return a clear structured denial to the agent/user and MUST NOT partially apply the change.
- **FR-020**: When a mutation is allowed by flags but denied by cluster RBAC (user creds), the system MUST surface the authorization failure in the **tool result and resulting assistant text** (and MAY set response metadata such as `kube_denied`); it MUST NOT escalate privileges.
- **FR-021**: Agent tooling that reaches the cluster MUST go exclusively through the Python wrapper surface; non-wrapper cluster mutation paths available to the agent MUST be removed or hard-disabled.
- **FR-022**: Free-text recommendations (including suggested commands the user could run themselves) MUST be allowed even when mutate flags are off.
- **FR-023**: Automated tests MUST cover: (a) mutate flag off blocks wrapper mutations, (b) recommendations still appear in text when mutate off, (c) only wrapper entrypoints used for cluster I/O in the agent tool registry.
- **FR-024**: Chart **defaults** MUST ship safe policy: mutate off; methods GET-only; dangerous subresources denied; Secrets **identify-only** (see FR-025). Defaults live under Helm `kubeApi` (see chart `values.yaml` and access-model contract).
- **FR-025**: Secret handling defaults: wrappers MAY list/identify Secrets (name, namespace, type, labels, **data key names only**). Wrappers MUST NOT return Secret `data` / `stringData` values to the agent. Secret create/update/delete via wrappers MUST be denied by default.
- **FR-026**: Policy enforcement MUST be implemented as a **single chokepoint** on the approved Python kube wrapper path (not duplicated across prompts, skills, or multiple ad-hoc clients). Free-text recommendations MUST NOT pass through this gate.

### How wrapper policy is enforced (normative design)

Policy is **many settings, one gate** — not a large parallel codebase.

#### Layers

```text
User message
  → Model may recommend freely (no policy check)
  → If agent calls a cluster tool:
       1. Load KubeApiPolicy once at process start (from env ← Helm values)
       2. authorize(request) → allow | deny{reason}
       3. On allow: call Kubernetes API using the user's credentials
       4. redact(response) for Secrets (and fail closed on secret values)
       5. Return tool result to the model
```

| Layer | Role |
|-------|------|
| Helm `kubeApi` / env | What **this deployment** will attempt or return |
| Single Python authorize gate | Evaluates each wrapper request against policy |
| User credentials | Final **cluster RBAC** on the wire |
| System prompt | Only “use wrappers for cluster I/O” — not a second security system |

#### Single chokepoint

- All agent cluster I/O MUST enter through the approved wrapper entry (today: the shared kube API tool path; any future wrappers MUST call the same authorize + redact helpers).
- Policy MUST NOT be re-implemented in chat handlers, skills, or the LLM prompt.
- Bypass clients available to the agent are out of scope / forbidden (FR-021).

#### Policy object (loaded once)

At startup the process builds one immutable policy from environment variables mapped from chart defaults, including at least:

- `allowRead`, `allowMutate`, `allowedMethods`
- namespace mode + list; optional resource / API group / subresource allowlists
- `secrets.allowIdentify`, `secrets.allowReadData`, `secrets.allowMutate`
- deny flags: serviceaccounts, cluster-scoped writes, exec, portforward, proxy
- `dryRunMutations`, `logDeniedRequests`

Chart defaults (product baseline):

- Mutate **off**; methods **GET** only
- Secrets: **identify yes, data no, mutate no**
- exec / portforward / proxy / SA / cluster-scoped writes: **denied**

#### Evaluation order for each wrapper request

Given method, API group, resource, namespace, name, subresource:

1. Method valid (GET/POST/PUT/PATCH/DELETE)? Else deny.
2. **Read vs mutate**: GET requires `allowRead`; other methods require `allowMutate` **and** method ∈ `allowedMethods`.
3. **Secrets policy**:
   - LIST / metadata identify allowed only if `secrets.allowIdentify`
   - Returning secret **values** forbidden unless `secrets.allowReadData`
   - Create/update/delete secrets forbidden unless global mutate **and** `secrets.allowMutate`
4. Other **deny** rules (serviceaccounts, exec, portforward, proxy, cluster-scoped writes).
5. Namespace mode (any / allowlist / denylist) if configured.
6. Resource / API group allowlists if non-empty.
7. Subresource allowlist if non-empty; deny exec/portforward/proxy when configured.
8. Optional dry-run for mutations.
9. **Then** perform the API call with **user credentials**.
10. **Post-redact**: if resource is Secret (or response contains Secret-like data) and `allowReadData` is false, strip `data` / `stringData` values; MAY retain key **names** only for identify.

First failing step wins → structured denial, e.g. `{ "blocked": true, "reason": "mutate_disabled" | "secrets_data_forbidden" | ... }`, no partial apply.

#### Secrets: identify vs read (product rule)

| Allowed by default | Not allowed by default |
|--------------------|-------------------------|
| List Secrets | Return `data` / `stringData` **values** to the agent |
| Metadata (name, namespace, type, labels, annotations) | Create / update / delete Secrets via wrappers |
| **Key names only** on the secret | |

Even if the API server returns secret data, the wrapper MUST redact before the tool result is visible to the model.

#### What policy does not gate

- Natural-language remediation recommendations
- User running suggested commands outside the product
- Vestige memory writes (separate scrubber; must not store secret values)

#### Implementation expectation (size / structure)

Enforcement SHOULD stay a small dedicated module (policy load + authorize + redact) invoked from the existing cluster tool path—not scattered conditionals across the app. Correctness is proven with **table-driven tests** over (method, resource, subresource, policy) → allow or reason.

### Key Entities

- **Memory record** / **Recall result** / **Chat turn** / **Memory service** / **Legacy KB entry** — as in prior memory design.
- **Kube API wrapper policy**: Helm `kubeApi` → env → single policy object controlling what wrappers will execute or return (see enforcement section).
- **Wrapper request**: method, group, version, resource, namespace, name, subresource (input to authorize).
- **Policy denial**: structured blocked tool result with stable reason code.
- **User cluster credentials**: Short-lived Kion/AWS or kubeconfig context used for API authz against the real cluster after policy allow.
- **Agent instruction set**: Minimal prompt content after guard-stripping (persona, format, “wrappers only,” live evidence first).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: ≥90% of test troubleshooters complete multi-step diagnosis without manual KB save.
- **SC-002**: For 10 seeded prior incidents, relevant prior lesson in first response for ≥8/10 (human-graded).
- **SC-003**: After pod restarts, ≥95% of 20 auto-saved items still recallable.
- **SC-004**: With memory stopped, ≥95% of chat requests still return live-grounded answers within normal timeout.
- **SC-005**: Zero Save-to-KB entry points in primary chat UI after release.
- **SC-006**: Core memory is cluster volume–backed; no external hosted vector DB in prod config.
- **SC-007**: CI suite covers auto-recall, auto-save, Save-to-KB removal without live prod cluster.
- **SC-008**: In a fixed script of 10 “how do I fix X?” prompts, **≥9/10** responses include concrete remediation recommendations without multi-step verbal approval ceremony (human-graded).
- **SC-009**: With mutate flags off, **100%** of attempted mutating wrapper calls in test harness are denied and leave fixture cluster state unchanged.
- **SC-010**: Prompt corpus after change contains **no** instructions that forbid recommending remediations or that require dual chat approval for advice (checklist review).
- **SC-011**: With default policy, Secret LIST/metadata works in tests; tool payloads never include base64 Secret values; Secret data GET is blocked or fully redacted (100% of test cases).
- **SC-012**: All agent cluster tool calls in the test suite pass through a single authorize path (no unscoped client usage in tool registry).
- **SC-013**: Table-driven policy tests cover at least: default GET allow, default mutate deny, secret identify vs data deny, exec deny, mutate-on with method allowlist.

## Assumptions

- Vestige remains the memory backend (spike GO); HTTP MCP service topology preferred.
- Shared team memory per deployment namespace.
- No FAISS dual-write after cutover.
- AGPL Vestige acceptable as separate process.
- **Recommendations ≠ execution**: product intentionally allows advice while blocking execution in code.
- Mutate flags are operator-controlled per environment (dev may enable; prod default off).
- Constitution **v3.0.0** already matches code-enforced access; implement against v3.
- User credentials remain the real RBAC boundary for allowed API verbs when mutations are flag-enabled.
- **SC-001, SC-002, SC-003, SC-008** are release/manual validation metrics (see tasks Phase 8 checklist), not CI gates.

## Out of Scope

- Replacing K8sGPT weather pipeline.
- Company-wide wiki UI or multi-tenant SaaS memory mesh.
- Perfect secret redaction for all free text.
- Teaching the model never to “sound like kubectl” (allowed as recommendation text).
- Building a full policy engine beyond wrapper flags + user RBAC (e.g. OPA) in this feature—flags + creds are the two layers.

## Dependencies

- Existing agentic chat loop and Python kube client/wrapper stack.
- Vestige packaging + MCP client (memory workstream).
- GitOps charts for chatbot + memory.
- Constitution v3.0.0 (already amended on this branch).

## Risks

- **Over-permissive flags in prod**: mitigate with default-off + GitOps review.
- **Users confuse recommendation with “bot did it”**: UI/copy may clarify advice vs applied change (optional polish).
- **Model invents successful mutation**: tool results must be authoritative; don’t claim success without wrapper success.
- **AGPL / model cache / single-writer** as in memory spike.
- **Constitution drift**: keep code aligned with v3.0.0; do not reintroduce chat dual-approval as auth.
