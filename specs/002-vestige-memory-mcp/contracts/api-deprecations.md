# Contract: HTTP API / UI deprecations

## Removed user-facing KB write path

| Surface | Before | After cutover |
|---------|--------|---------------|
| UI | `SolutionSubmitDialog` in chat | **Removed** — no Save-to-KB control |
| Client | `solutionsApi.submitSolution` | **Removed** |
| API | `POST /api/solutions` (and list if only for KB browser) | **410 Gone** with body `{ "detail": "Knowledge base save removed; memory is automatic via Vestige." }` **or** route deleted if no external clients |

Prefer **410** for one release if any external automations called solutions API; then delete.

## Chat API (stable with additive metadata)

`POST /api/chat/query` remains.

**Additive optional fields** on `ChatResponse.metadata` (non-breaking):

```json
{
  "memory_degraded": false,
  "memory_hits": 3,
  "memory_ingested": true,
  "memory_ingest_status": "stored"
}
```

No requirement for frontend to display these in MVP (optional debug).

## Unchanged

- Auth credentials APIs  
- Clusters / weather  
- Conversation history endpoints  

## OpenAPI

Regenerate or hand-update so solutions write endpoints are marked deprecated/removed before release.
