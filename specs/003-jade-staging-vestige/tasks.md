# Tasks: JADE Staging Vestige Deploy (003)

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [contracts/gitlab-deploy.md](./contracts/gitlab-deploy.md)  
**Prerequisites**: Spec quality checklist complete

## Format

- **[P]**: Can run in parallel
- **[USn]**: User story mapping
- Paths: GitLab unless marked **(GitHub)**

---

## Phase 1: Setup (spec-kit + inventory)

- [x] T001 Create feature dir `specs/003-jade-staging-vestige/` with spec, plan, research, data-model, contracts, quickstart **(GitHub)**
- [x] T002 [P] Write requirements checklist and mark validation complete **(GitHub)**
- [ ] T003 Record pre-cutover `jadeuc-staging-b` SHA + image tags from `chart/values-override.yaml` and `clusters/jade-2pst-b/devops-chatbot.values.yaml` into quickstart notes or task log
- [ ] T004 [P] Confirm `glab` auth and Maintainer access on project 5003

---

## Phase 2: Foundational (blocking)

**⚠️ CRITICAL**: Snapshot and image line before rewriting staging

- [ ] T005 [US1] Create and push GitLab branch `jadeuc-faiss` from current `jadeuc-staging-b` tip (project 5003)
- [ ] T006 [US1] Verify `jadeuc-faiss` commit equals pre-cutover staging tip; document image pin on that branch
- [ ] T007 [US2] Clone/checkout GitLab `bookish-octo-robot` `main` as port target
- [ ] T008 [US2] Inventory delta vs GitHub `002-vestige-memory-mcp` (files to add/remove: memory, kube_policy, kb/solutions, Dockerfile, helm)
- [ ] T009 Resolve Vestige binary strategy for JADE builders (curl allowlist **or** vendor under agreed path); document choice in MR description

**Checkpoint**: Snapshot exists; main checkout ready; binary strategy chosen

---

## Phase 3: User Story 2 — Vestige-capable image on main (P1) 🎯 MVP core

**Goal**: GitLab `main` builds and pushes 002-equivalent image

- [ ] T010 [US2] Port `backend/memory/` and `backend/kube_policy/` (and related chat/session/EKS refresh code) from GitHub 002 to GitLab main
- [ ] T011 [P] [US2] Port frontend KB/Save-to-KB removal and apiError handling as required for 002 parity
- [ ] T012 [P] [US2] Remove FAISS/KB packages and seeder/solutions paths from GitLab main (mirror 002 deletions)
- [ ] T013 [US2] Update GitLab main `Dockerfile`: drop devops-kb; add vestige + supervisord scripts; USER 1000; healthcheck `/api/health`
- [ ] T014 [P] [US2] Port `docker/supervisord.conf`, `start-backend.sh`, `start-vestige.sh`
- [ ] T015 [US2] Update GitLab main `helm/devops-chatbot` with `memory.*`, `kubeApi.*`, Results-only rbac template, env wiring, vestige init dirs, probes
- [ ] T016 [US2] Adjust GitLab main tests/CI for removed FAISS modules; ensure package pipeline green
- [ ] T017 [US2] Merge to `main` and capture published image short SHA from successful pipeline

**Checkpoint**: Registry contains Vestige-capable `devops-chatbot:<sha>`

---

## Phase 4: User Story 1 + 3 — Replace jadeuc-staging-b (P1)

**Goal**: Staging deploy line points at Vestige image with grown PVC and vestige env

- [ ] T018 [US1][US3] Checkout `jadeuc-staging-b` and sync `chart/` from updated main helm **without** wiping JADE cluster/ingress/Vault sections
- [ ] T019 [US3] Set `MEMORY_BACKEND=vestige` and Vestige URL/dir values in chart defaults and/or `clusters/jade-2pst-b/devops-chatbot.values.yaml`
- [ ] T020 [US3] Increase PVC size (target 40Gi) and memory requests/limits (target 1Gi/2Gi) in staging overlay
- [ ] T021 [US2] Pin `image.tag` to main Vestige short SHA in `chart/values-override.yaml` and cluster overlay (keep consistent)
- [ ] T022 [US2] Restore probes to `/api/health` and `/api/health/ready`; remove root-path probe override
- [ ] T023 [US2] Remove `KB_SEEDING_*` env from staging deployment templates
- [ ] T024 [US2] Push `jadeuc-staging-b`; confirm deploy pipeline / Argo sync success

**Checkpoint**: Staging Application Healthy; pod Ready

---

## Phase 5: User Story 4 — Security posture (P2)

**Goal**: Results-only SA + mutate-off policy on staging

- [ ] T025 [US4] Replace staging `k8s/rbac.yaml` broad ClusterRole with Results-only rules bound to chatbot SA in `bookish-octo-robot` namespace
- [ ] T026 [US4] Confirm chart/env `kubeApi.allowMutate=false` (and related defaults) present on staging render (`helm template` or live env)
- [ ] T027 [US4] Smoke: user session can still diagnose live resources; pod SA cannot list Secrets cluster-wide

---

## Phase 6: Smoke, rollback doc, operator gate

- [ ] T028 [US2][US3] Staging smoke: URL load, health, login, cluster select, one chat turn, no Save-to-KB UI
- [ ] T029 [US3] Confirm vestige data dir on PVC (exec or logs); note model-cache after first memory use
- [ ] T030 [US1] Document rollback steps in GitLab staging README (point at `jadeuc-faiss` + prior image pin)
- [ ] T031 [US4] If Results/weather broken after SA tighten only: open operator follow-up; otherwise leave operator repo untouched
- [ ] T032 [P] Commit/push GitHub `specs/003-jade-staging-vestige/` on branch `003-jade-staging-vestige` or fold into 002 PR as docs

---

## Dependencies

```text
T001-T002 (done)
    → T003-T004
    → T005-T006 (snapshot) ──┐
    → T007-T009              │
    → T010-T017 (main image)─┼→ T018-T024 (staging replace)
                             → T025-T027 (RBAC)
                             → T028-T032 (smoke/docs)
```

## Parallel opportunities

- T010 / T011 / T012 after T008
- T013 / T014 / T015 after binary strategy T009
- T025 can start once chart templates exist (T018) even before image pin if RBAC is independent

## Implementation strategy

1. **MVP**: T005–T006 + T010–T017 + T018–T024 + T028 (staging live on Vestige image)
2. **Hardening**: T025–T027 + T029–T030
3. **Escalation**: T031 only if needed

## Notes

- Do not merge operator changes unless T031 triggers.
- Do not delete `jadeuc-faiss` after cutover.
