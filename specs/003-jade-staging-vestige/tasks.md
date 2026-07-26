# Tasks: JADE Staging Vestige Deploy (003)

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [contracts/gitlab-deploy.md](./contracts/gitlab-deploy.md)  
**Prerequisites**: Spec quality checklist complete  
**Synced**: 2026-07-26 (vendor-first; PVC ≥10Gi; image re-pin rollback primary; preserve conversations; local pytest OK)

## Format

- **[P]**: Can run in parallel
- **[USn]**: User story mapping
- Paths: GitLab unless marked **(GitHub)**

---

## Phase 1: Setup (spec-kit + inventory)

- [x] T001 Create feature dir `specs/003-jade-staging-vestige/` with spec, plan, research, data-model, contracts, quickstart **(GitHub)**
- [x] T002 [P] Write requirements checklist and mark validation complete **(GitHub)**
- [ ] T003 Record pre-cutover `jadeuc-staging-b` SHA + image tags + PVC size from `chart/values-override.yaml` and `clusters/jade-2pst-b/devops-chatbot.values.yaml` into [quickstart.md](./quickstart.md) notes or task log (overlay **jade-2pst-b** / EKS **jade-2pst-b-rgp**)
- [ ] T004 [P] Confirm `glab` auth and Maintainer access on project 5003

---

## Phase 2: Foundational (blocking)

**⚠️ CRITICAL**: Snapshot and image line before rewriting staging. **T009 (vendor binaries) MUST complete before T013–T014.**

- [ ] T005 [US1] Create and push GitLab branch `jadeuc-faiss` from current `jadeuc-staging-b` tip (project 5003) — FR-001
- [ ] T006 [US1] Verify `jadeuc-faiss` commit equals pre-cutover staging tip; document image pin on that branch — SC-001
- [ ] T007 [US2] Clone/checkout GitLab `bookish-octo-robot` `main` as port target
- [ ] T008 [US2] Inventory delta vs GitHub `002-vestige-memory-mcp` (files to add/remove: memory, kube_policy, kb/solutions, Dockerfile, helm)
- [ ] T009 [US2] **Vendor-first**: obtain Vestige **v2.2.1** linux binaries into build context (`third_party/vestige/` or internal mirror path); record path in MR and [contracts/gitlab-deploy.md](./contracts/gitlab-deploy.md); **no public GitHub curl happy path** — **blocks Dockerfile tasks** — FR-002

**Checkpoint**: Snapshot exists; main checkout ready; vendored binaries present

---

## Phase 3: User Story 2 — Vestige-capable image on main (P1) 🎯 MVP core

**Goal**: GitLab `main` builds and pushes 002-equivalent image with automated test gate

- [ ] T010 [US2] Port `backend/memory/` and `backend/kube_policy/` (and related chat/session/EKS refresh code) from GitHub 002 to GitLab main — FR-002, FR-012
- [ ] T011 [P] [US2] Port frontend KB/Save-to-KB removal and apiError handling as required for 002 parity — FR-006
- [ ] T012 [P] [US2] Remove FAISS/KB packages and seeder/solutions paths from GitLab main (mirror 002 deletions) — FR-006
- [ ] T013 [US2] Update GitLab main `Dockerfile`: drop devops-kb; **COPY vendored** vestige + supervisord scripts; USER 1000; healthcheck `/api/health` — FR-002 (**depends on T009**)
- [ ] T014 [P] [US2] Port `docker/supervisord.conf`, `start-backend.sh`, `start-vestige.sh` (**depends on T009**)
- [ ] T015 [US2] Update GitLab main `helm/devops-chatbot` with `memory.*`, `kubeApi.*` (allowMutate false, free recommendations allowed), Results-only rbac template, env wiring, vestige init dirs, probes — FR-002, FR-007
- [ ] T016 [US2] Adjust GitLab main tests for removed FAISS modules; ensure local/any-runner pytest can run against ported tree
- [ ] T016b [US2] **Constitution test gate (SC-008)**: Run pytest covering `backend/memory` + `backend/kube_policy` (mutate-off defaults, secret identify-only, degraded-memory if present) **locally or on any runner**; attach green output to MR or task log — **required before T017** (GitLab CI pytest job optional)
- [ ] T017 [US2] Merge to `main` only after T016b green; capture published image short SHA from successful package pipeline — FR-002

**Checkpoint**: Registry contains Vestige-capable `devops-chatbot:<sha>`; pytest gate recorded

---

## Phase 4: User Story 1 + 3 + 4 — Replace jadeuc-staging-b (P1) 🎯 MVP includes security

**Goal**: Staging deploy line points at Vestige image with PVC ≥10Gi (keep-as-is if already), vestige env, preserve conversations, **and** Results-only SA + mutate-off **before first push/sync**

- [ ] T018 [US1][US3] Checkout `jadeuc-staging-b` and sync `chart/` from updated main helm **without** wiping JADE cluster/ingress/Vault/TLS/pull-secret/ResourceQuota-off/PDB-off/Recreate sections — FR-009
- [ ] T019 [US3] Set `MEMORY_BACKEND=vestige` and Vestige URL/dir values in chart defaults and/or `clusters/jade-2pst-b/devops-chatbot.values.yaml` — FR-003, SC-004
- [ ] T020 [US3] Ensure PVC size **≥10Gi** in staging overlay — keep existing size if already ≥10Gi; grow only if below 10Gi; **do not target 40Gi** — FR-004, SC-005
- [ ] T020b [US3] If PVC is **below 10Gi** and cannot grow in place **without** destroying conversations: stop and document platform path that preserves FR-013; do not default to wipe/recreate — FR-004, FR-013
- [ ] T021 [US2] Pin `image.tag` to main Vestige short SHA in `chart/values-override.yaml` and cluster overlay (keep consistent) — FR-003
- [ ] T022 [US2] Restore probes to `/api/health` and `/api/health/ready`; remove root-path probe override — FR-005, SC-003
- [ ] T023 [US2] Remove `KB_SEEDING_*` env from staging deployment templates — FR-006
- [ ] T025 [US4] Replace staging `k8s/rbac.yaml` broad ClusterRole with Results-only rules bound to chatbot SA in `bookish-octo-robot` namespace — FR-008 (**before T024**)
- [ ] T026 [US4] Confirm chart/env `kubeApi.allowMutate=false` (and related defaults) present on staging render (`helm template` or dry-run) — FR-007 (**before T024**)
- [ ] T024 [US2][US4] Push `jadeuc-staging-b` only after T018–T023 + T025–T026; confirm deploy pipeline / Argo sync success — SC-003

**Checkpoint**: Staging Application Healthy; pod Ready; Results-only SA + mutate-off already applied

---

## Phase 5: Smoke, rollback doc, operator gate (MVP completion)

**Goal**: Prove US2–US4 acceptance and document rollback (image re-pin primary)

- [ ] T027 [US4] Security smoke — FR-007, FR-008, SC-007, SC-009a:
  - user session can diagnose live resources (session clients)
  - pod SA cannot list Secrets cluster-wide
  - free-text remediation recommendation still appears with mutate off (one chat turn that asks for recommended fix / YAML)
- [ ] T028 [US2][US3] Staging functional smoke — SC-002, SC-003, SC-004, SC-009, SC-010:
  - URL load (`https://k8s-assistant.staging.jadeuc.com`)
  - `/api/health` and `/api/health/ready` OK
  - login + cluster select + one chat turn
  - no Save-to-KB UI
  - FR-009 quick check: ingress host, login (Vault LLM), no unexpected ResourceQuota block
  - note: degraded-memory behavior covered by T016b unit tests (list test names) **or** optional kill-vestige smoke if safe
  - note FR-012: memory remains cluster-scoped per 002 (not per-user)
  - **SC-010 / FR-013**: spot-check pre-cutover `/data/conversations` still present (exec or history API)
- [ ] T029 [US3] Confirm vestige data dir on PVC (exec or logs); note model-cache if created after first memory use — FR-003, SC-004
- [ ] T030 [US1] Document rollback in GitLab staging README (or `docs/`) with **concrete** steps — FR-010, SC-006:
  - **Primary — image re-pin**: on `jadeuc-staging-b`, set `image.tag` to pre-cutover FAISS pin from T003/`jadeuc-faiss` values; push; wait for sync
  - **Secondary — branch/Argo**: retarget Application source branch to `jadeuc-faiss` (or platform `jade-update-argo` equivalent)
  - Note PVC may retain `/data/vestige` after rollback (harmless); conversations preserved
- [ ] T031 [US4] If Results/weather broken after SA tighten only: open operator follow-up; otherwise leave operator repo untouched — FR-011
- [ ] T032 [P] Commit/push GitHub `specs/003-jade-staging-vestige/` on branch **`003-jade-staging-vestige`** only (do not fold into 002 PR) **(GitHub)**

---

## Dependencies

```text
T001-T002 (done)
    → T003-T004
    → T005-T006 (snapshot) ────────────┐
    → T007-T008                        │
    → T009 (vendor binaries) ──┐       │
    → T010-T012 (after T008)   │       │
    → T013-T015 (after T009) ──┘       │
    → T016 → T016b (pytest gate)       │
    → T017 (merge + SHA) ──────────────┼→ T018-T023
                                       → T020b only if PVC <10Gi blocked
                                       → T025-T026 (RBAC/policy render)
                                       → T024 (push/sync)
                                       → T027-T030 (smoke + rollback)
                                       → T031 (only if Results fail)
                                       → T032 (docs branch)
```

## Parallel opportunities

- T010 / T011 / T012 after T008 (not before T009 for Dockerfile)
- T013 / T014 / T015 only after T009
- T025–T026 after T018 (chart present); **must finish before T024**
- T032 can run anytime after T001

## Implementation strategy

1. **MVP (full acceptance)**: T005–T006 + T009–T017 + T018–T026 + T024 + T027–T030  
   - Staging live on Vestige image **with** Results-only SA, mutate-off, probes, PVC ≥10Gi (keep-as-is OK), conversations preserved, smoke + image-re-pin rollback docs  
2. **Escalation only**: T031 if Results/weather fail after SA tighten  
3. **Do not** declare cutover complete without Phase 5 smoke (T027–T030)

## Notes

- Do not merge operator changes unless T031 triggers.
- Do not delete `jadeuc-faiss` after cutover.
- US4 is P1 for acceptance (security on first Vestige sync).
- Package-only GitLab CI is insufficient without T016b (local green log is enough).
- Do not wipe `/data/conversations` or recreate PVC by default.
