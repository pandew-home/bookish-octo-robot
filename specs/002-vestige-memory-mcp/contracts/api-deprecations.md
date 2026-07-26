# Contract: HTTP API / UI deprecations

## Removed user-facing KB write path

Never shipped to production — routes and UI were **deleted** entirely (no 410 stub).

| Surface | Status |
|---------|--------|
| UI | `SolutionSubmitDialog` **removed** |
| Client | `solutionsApi` / solution types **removed** |
| API | `backend/api/solutions.py` **deleted** (no `/api/solutions` or `/api/kb/search`) |

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
