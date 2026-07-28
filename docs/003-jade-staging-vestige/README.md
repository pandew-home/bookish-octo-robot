# 003 — JADE staging Vestige cutover

Delivery plan for integrating GitHub `002-vestige-memory-mcp` into this repo's
**jadeuc-staging-b** deploy line (jade-2pst-b).

**Source of product code:** GitHub `pandew-home/bookish-octo-robot` branch `002-vestige-memory-mcp`.

**Operator repo:** out of scope for MVP (`bookish-octo-robot-operator`) unless smoke fails after SA tighten.

## Start here

1. [spec.md](./spec.md) — requirements and acceptance
2. [plan.md](./plan.md) — technical approach
3. [tasks.md](./tasks.md) — ordered execution checklist
4. [quickstart.md](./quickstart.md) — cutover runbook
5. [contracts/gitlab-deploy.md](./contracts/gitlab-deploy.md) — branch/image contract

## Branch hygiene (this repo)

1. Snapshot current `jadeuc-staging-b` → `jadeuc-faiss` (FAISS rollback)
2. Port 002 into `main` (image build)
3. Replace `jadeuc-staging-b` chart/overlays for Vestige
