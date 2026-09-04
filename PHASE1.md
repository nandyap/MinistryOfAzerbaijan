# Phase 1: Orchestrator API for Backend Integration

A safe, simple, stable API surface for integrating the orchestrator with a third-party platform.

## What's included

| File | Purpose |
| --- | --- |
| [PHASE1_API.md](PHASE1_API.md) | Complete API reference with all endpoints and examples |
| [backend_client.py](../samples/backend_client.py) | Python client library (sync) |
| [backend_integration_example.ps1](../samples/backend_integration_example.ps1) | PowerShell examples testing all endpoints |

## Key design principles

✅ **Non-breaking.** The existing `/orchestrator` endpoint is unchanged. These are pure additive endpoints.  
✅ **Simple.** Server-to-server calling only — no JWT validation, no browser complications.  
✅ **Reversible.** Instant rollback by shifting traffic or killing the revision.

## What's new

### Endpoints

| Endpoint | Purpose | Auth |
| --- | --- | --- |
| `GET /health` | Gateway health probe | None |
| `POST /chat` | Ask + get JSON answer | API key + user ID |
| `GET /conversations` | List conversations | API key + user ID |
| `GET /conversations/{id}` | Full history & feedback | API key + user ID |
| `GET /feedback` | All feedback for user | API key + user ID |

### Data changes

Conversations now record:

- `client_principal_id` — the teacher's user ID (from `X-User-Id` header)
- `created_at`, `updated_at` — ISO-8601 timestamps
- **`answer` text** inside each question turn (previously not persisted!)

This means history queries work properly for the first time.

### Authentication

Two headers, both required (except `/health`):

```
X-API-KEY: <your-orchestrator-api-key>
X-User-Id: <teacher-uuid>
```

The backend sends both; the orchestrator does not validate the user ID. **Your backend is responsible for proving the user is authenticated.**

## Testing from your VM

You already have network access to the internal Container App. Try this:

```powershell
$fqdn = "ca-epj2ijiie4drm-orchestrator.purplebay-4a93a1b6.swedencentral.azurecontainerapps.io"
$key = "<orchestrator-api-key>"

# 1. Health check (no auth needed)
curl https://$fqdn/health

# 2. Ask a question
curl -X POST "https://$fqdn/chat" `
  -H "Content-Type: application/json" `
  -H "X-API-KEY: $key" `
  -H "X-User-Id: test-teacher-001" `
  -d '{"ask":"What is 2+2?"}'

# 3. List conversations
curl "https://$fqdn/conversations" `
  -H "X-API-KEY: $key" `
  -H "X-User-Id: test-teacher-001"
```

If you get JSON back, the API is working. If you get a TLS error, the internal certificate chain might not be trusted locally — you can use `curl -k` to skip verification in dev/test.

## Running the sample client

### PowerShell (recommended for your environment)

```powershell
# Edit backend_integration_example.ps1 to set:
# - $ORCHESTRATOR_URL
# - $ORCHESTRATOR_API_KEY
# - $TEACHER_ID

cd samples
.\backend_integration_example.ps1
```

This will run through all 6 examples and show you the full request/response cycle.

### Python

```bash
cd samples
pip install httpx
python backend_client.py
```

## Integrating with your platform

Your backend should follow this pattern:

```pseudocode
# Teacher submits a question in your UI
POST /api/your-platform/ask
  Input: { question, teacher_id }
  
  # Call orchestrator
  response = POST https://orchestrator/chat
    Headers: X-API-KEY, X-User-Id: teacher_id
    Body: { ask: question }
  
  # Store for later
  Save conversation_id + question_id locally
  
  # Return to UI
  Return { answer: response.answer, conversation_id, question_id }

# Teacher clicks 👍 or 👎
POST /api/your-platform/feedback
  Input: { conversation_id, question_id, is_positive, stars_rating }
  
  # Call orchestrator
  POST https://orchestrator/orchestrator
    Type: "feedback"
    conversation_id, question_id, is_positive, stars_rating
  
  # Return
  Return { status: "saved" }

# Teacher views their conversation history
GET /api/your-platform/conversations
  Input: { teacher_id }
  
  # Call orchestrator
  conversations = GET https://orchestrator/conversations
    Headers: X-User-Id: teacher_id
  
  # Return list (or store in your DB for caching)
  Return conversations

# Teacher opens a specific conversation
GET /api/your-platform/conversations/{id}
  Input: { conversation_id, teacher_id }
  
  # Call orchestrator
  detail = GET https://orchestrator/conversations/{id}
    Headers: X-User-Id: teacher_id
  
  # Return Q&A + feedback
  Return detail
```

## Deployment & rollout

### Phase 1a: Deploy & test (0% traffic)

```powershell
# Deploy new revision
az containerapp update -n ca-epj2ijiie4drm-orchestrator `
  -g rg-Azerbaijan_MoEd `
  --image <your-registry>.azurecr.io/gpt-rag-orchestrator:v1.1

# This creates a new revision with 0% traffic (inactive)
# Test it by hitting the revision-specific URL

# Get revision URL
az containerapp revision list -n ca-epj2ijiie4drm-orchestrator -g rg-Azerbaijan_MoEd `
  --query "[0].properties.trafficWeight" -o json
```

### Phase 1b: Shift traffic

Once you've tested and are confident:

```powershell
# Shift 10% traffic to the new revision
az containerapp ingress traffic set -n ca-epj2ijiie4drm-orchestrator `
  -g rg-Azerbaijan_MoEd `
  --revision-weights <new-revision-name>=10 <old-revision-name>=90

# Monitor for errors
# If good, shift to 100%
# If bad, roll back instantly to 0%
```

### Phase 1c: Rollback (if needed)

```powershell
# Instant rollback to previous revision
az containerapp ingress traffic set -n ca-epj2ijiie4drm-orchestrator `
  -g rg-Azerbaijan_MoEd `
  --revision-weights <old-revision-name>=100 <new-revision-name>=0
```

## Important notes

### ⚠️ API Key is not set yet

If `ORCHESTRATOR_APP_APIKEY` is not configured in App Configuration or Key Vault, the API key check is **skipped** and every request is allowed. Before exposing this, you must:

1. Generate a random API key
2. Store it in Key Vault
3. Configure App Configuration to reference it: `ORCHESTRATOR_APP_APIKEY = @Microsoft.KeyVault(SecretUri=https://...)`

### ⚠️ No historical data pre-upgrade

Conversations created before Phase 1 have:
- No `client_principal_id` (owner field)
- No stored answers
- No timestamps

So they won't show in `GET /conversations` queries. This is not a problem if you're just launching, but if you have existing data, note that backfill is not automatic.

### ⚠️ No rate limiting (yet)

If your platform has thousands of teachers each asking questions simultaneously, we should discuss:
- Per-user rate limits (e.g., 100 questions/hour)
- Token budgets (answers consume Azure OpenAI tokens)
- Queue/backpressure strategy

### Feedback goes to `/orchestrator`, not `/chat`

Feedback is submitted to the *existing* `/orchestrator` endpoint with `"type": "feedback"`. This is intentional — it keeps the old and new code paths separate for safety.

### Document upload (separate service: `gpt-rag-ingestion`)

A new `POST /documents/upload` endpoint was added to the **ingestion** service (different Container App, different API key: `INGESTION_APP_APIKEY`). It uploads a file to blob storage and triggers indexing immediately, so it's searchable within seconds. Once uploaded, reference the filename via `uploaded_files` on `/chat`.

**⚠️ Not yet resolved — needs customer input before wide rollout:**
1. **No ownership scoping.** Uploaded documents aren't tied to the uploading teacher — any user can reference any filename. Fixing this properly requires tagging indexed chunks with an owner ID and filtering search by it (moderate-size change, touches the indexer, the search index schema, and the `/chat` query path — see implementation doc for details).
2. **No retention policy.** Files are stored forever with no cleanup, unlike the original chatbot's 24-hour temp-upload behavior. At scale this needs a decision: keep forever (matches "teacher grades a test days later" use case), or add expiry/cleanup.
3. **No self-service list/delete for teachers.**

Do not treat document upload as production-ready for multi-tenant use until these are addressed.

## Next phase

If you need **streaming answers** (typewriter UX instead of waiting for the full response), we can add `POST /chat/stream` that returns Server-Sent Events. For now, the JSON endpoint is simpler and easier to integrate.

## Support

- Interactive API docs: `https://ca-epj2ijiie4drm-orchestrator.purplebay-4a93a1b6.swedencentral.azurecontainerapps.io/docs`
- OpenAPI schema: `https://ca-epj2ijiie4drm-orchestrator.purplebay-4a93a1b6.swedencentral.azurecontainerapps.io/openapi.json`
- Questions? See [PHASE1_API.md](PHASE1_API.md)
