# GPT-RAG Orchestrator Phase 1 API

Working API surface for backend-to-orchestrator integration.

---

## Quick Start

```powershell
# 1. Find your orchestrator FQDN (internal, VNet-only)
$fqdn = az containerapp show -n ca-epj2ijiie4drm-orchestrator `
  -g rg-Azerbaijan_MoEd `
  --query properties.configuration.ingress.fqdn -o tsv

# 2. Get your API key from Key Vault or App Configuration
$apiKey = "<your-orchestrator-api-key>"

# 3. Ask a question
curl -X POST "https://$fqdn/chat" `
  -H "Content-Type: application/json" `
  -H "X-API-KEY: $apiKey" `
  -H "X-User-Id: teacher-uuid-12345" `
  -d '{"ask":"What is 2+2?"}'
```

---

## Authentication

Two headers, both required for all endpoints (except `/health`):

| Header | Value | Purpose |
| --- | --- | --- |
| `X-API-KEY` | Orchestrator API key | Proves your backend is allowed to call this API |
| `X-User-Id` | Teacher/user UUID | Scopes conversations & feedback to this user (backend provides it) |

**Critical:** The backend sends `X-User-Id`; the orchestrator does not validate it. Your backend is responsible for authenticating the teacher and verifying the user ID before sending it to us.

---

## Endpoints

### `GET /health`

Unauthenticated liveness probe for gateway health checks.

```bash
curl https://ca-epj2ijiie4drm-orchestrator.purplebay-4a93a1b6.swedencentral.azurecontainerapps.io/health
```

---

### `POST /documents/upload` (ingestion service, separate deployment)

Uploads a document to blob storage and triggers indexing immediately so it becomes searchable.

> **Note:** This runs on the `gpt-rag-ingestion` service, not the orchestrator. It has its own FQDN and its own API key (`INGESTION_APP_APIKEY`), set separately from the orchestrator's key.

```bash
curl -X POST "https://<ingestion-fqdn>/documents/upload" \
  -H "X-API-KEY: <ingestion-api-key>" \
  -F "file=@/path/to/document.pdf"
```

**Response:**
```json
{
  "status": "uploaded",
  "filename": "document.pdf",
  "container": "documents",
  "indexing_status": "completed"
}
```

**Supported file types:** `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md`, `.html`, `.csv`, `.xlsx`, `.xls`

**Limits:** Max file size configurable via `MAX_UPLOAD_SIZE_MB` (default 50 MB). Empty files rejected.

**After upload:** Reference the exact filename in the `uploaded_files` array on `/chat` to scope answers to that document:

```json
{ "ask": "Summarize this document", "uploaded_files": ["document.pdf"] }
```

**Known limitation — very small files:** Files with minimal content (e.g., a single short line) may not produce any indexable chunks and won't be searchable. This is expected chunker behavior, not a bug.

**⚠️ Open questions (unresolved, pending customer input):**
- **No per-user ownership/isolation.** Any caller can reference any previously uploaded filename in `uploaded_files` — there's no check that the file belongs to the requesting `X-User-Id`. A malicious or careless client could reference another teacher's uploaded document.
- **No retention/cleanup policy.** Uploaded documents are stored permanently with no expiry, unlike the original chatbot's 24-hour temporary upload folder. At scale (many teachers, many uploads), this means unbounded storage and search index growth.
- **No list/delete endpoint.** A teacher currently cannot see what they've uploaded or remove a file.

These need to be decided with the customer before broad rollout — see [PHASE1_CUSTOMER_WALKTHROUGH.md](PHASE1_CUSTOMER_WALKTHROUGH.md) slide on open questions.

**Response:**
```json
{ "status": "ok", "version": "1.0.0" }
```

---

### `POST /chat`

Ask a question, get back JSON with the answer (non-streaming).

**Request:**
```bash
curl -X POST "https://$fqdn/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: $apiKey" \
  -H "X-User-Id: teacher-12345" \
  -d '{
    "ask": "Summarize the 15th century Ottoman Empire",
    "conversation_id": null,
    "question_id": "q-001"
  }'
```

**Request fields:**
- `ask` (required): Your question
- `conversation_id` (optional): UUID from a previous turn to continue a conversation. If null/omitted, starts a new conversation.
- `question_id` (optional): Unique ID for this question, used to attach feedback. If not provided, one is generated.
- `user_context` (optional): Arbitrary JSON to pass to the orchestrator (e.g., `{"language":"sv"}`)
- `uploaded_files` (optional): List of file names to scope search results to

**Response:**
```json
{
  "conversation_id": "abc-123-def-456",
  "question_id": "q-001",
  "answer": "The Ottoman Empire in the 15th century was a rising power that...",
  "timestamp": "2026-09-03T11:30:45.123456+00:00"
}
```

**Response fields:**
- `conversation_id`: Use this in follow-up questions
- `question_id`: Use this to submit thumbs up/down feedback
- `answer`: The assistant's response (usually 200-1000 words depending on the question)
- `timestamp`: When the answer was completed

**Error responses:**
- `400`: Missing `ask` or `question` field
- `401`: Missing or invalid `X-API-KEY`
- `500`: Internal error generating answer

---

### `POST /orchestrator/feedback`

Submit thumbs up/down feedback on a specific answer.

**Request:**
```bash
curl -X POST "https://$fqdn/chat/feedback" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: $apiKey" \
  -H "X-User-Id: teacher-12345" \
  -d '{
    "type": "feedback",
    "conversation_id": "abc-123-def-456",
    "question_id": "q-001",
    "is_positive": true,
    "stars_rating": 5,
    "feedback_text": "Accurate and concise."
  }'
```

**Request fields:**
- `type`: Must be `"feedback"`
- `conversation_id` (required): The conversation you're rating
- `question_id` (optional): The specific turn. If omitted, defaults to the most recent question.
- `is_positive` (optional): `true` = 👍, `false` = 👎, `null` = not provided
- `stars_rating` (optional): 1–5 stars
- `feedback_text` (optional): Free-form comment (max 500 chars)

**Response:**
```json
{ "status": "success", "message": "Feedback saved successfully" }
```

---

### `GET /conversations`

List conversations for this user, most recently updated first.

**Request:**
```bash
curl "https://$fqdn/conversations?limit=50&offset=0" \
  -H "X-API-KEY: $apiKey" \
  -H "X-User-Id: teacher-12345"
```

**Query parameters:**
- `limit`: How many to return (default 50, max 200)
- `offset`: Skip this many (for pagination)

**Response:**
```json
{
  "conversations": [
    {
      "conversation_id": "abc-123",
      "client_principal_id": "teacher-12345",
      "created_at": "2026-09-03T10:00:00.000000+00:00",
      "updated_at": "2026-09-03T10:05:30.000000+00:00",
      "question_count": 3,
      "feedback_count": 2,
      "thumbs_up_count": 2,
      "thumbs_down_count": 0,
      "first_question": "Summarize the 15th century Ottoman Empire"
    }
  ],
  "count": 1
}
```

---

### `GET /conversations/{conversation_id}`

Full history for one conversation: all questions, all answers, all feedback.

**Request:**
```bash
curl "https://$fqdn/conversations/abc-123" \
  -H "X-API-KEY: $apiKey" \
  -H "X-User-Id: teacher-12345"
```

**Response:**
```json
{
  "conversation_id": "abc-123",
  "client_principal_id": "teacher-12345",
  "created_at": "2026-09-03T10:00:00.000000+00:00",
  "updated_at": "2026-09-03T10:05:30.000000+00:00",
  "question_count": 2,
  "feedback_count": 1,
  "thumbs_up_count": 1,
  "thumbs_down_count": 0,
  "first_question": "Summarize the 15th century Ottoman Empire",
  "questions": [
    {
      "question_id": "q-001",
      "text": "Summarize the 15th century Ottoman Empire",
      "answer": "The Ottoman Empire in the 15th century...",
      "asked_at": "2026-09-03T10:00:00.000000+00:00",
      "answered_at": "2026-09-03T10:00:15.000000+00:00"
    },
    {
      "question_id": "q-002",
      "text": "Who was Mehmed II?",
      "answer": "Mehmed II, known as 'the Conqueror'...",
      "asked_at": "2026-09-03T10:02:00.000000+00:00",
      "answered_at": "2026-09-03T10:02:10.000000+00:00"
    }
  ],
  "feedback": [
    {
      "question_id": "q-001",
      "is_positive": true,
      "stars_rating": 5,
      "feedback_text": "Accurate and concise.",
      "question_text": "Summarize the 15th century Ottoman Empire",
      "answer": "The Ottoman Empire in the 15th century..."
    }
  ]
}
```

---

### `GET /feedback`

Aggregate thumbs up/down across all of a user's conversations.

Useful for analytics: "What percentage of our answers do teachers rate positively?"

**Request:**
```bash
curl "https://$fqdn/feedback?limit=100" \
  -H "X-API-KEY: $apiKey" \
  -H "X-User-Id: teacher-12345"
```

**Response:**
```json
{
  "feedback": [
    {
      "conversation_id": "abc-123",
      "question_id": "q-001",
      "is_positive": true,
      "stars_rating": 5,
      "feedback_text": "Accurate and concise.",
      "question_text": "Summarize the 15th century Ottoman Empire",
      "answer": "The Ottoman Empire in the 15th century..."
    },
    {
      "conversation_id": "abc-123",
      "question_id": "q-002",
      "is_positive": true,
      "stars_rating": 4,
      "feedback_text": "Good but could use more detail on politics.",
      "question_text": "Who was Mehmed II?",
      "answer": "Mehmed II, known as 'the Conqueror'..."
    }
  ],
  "count": 2,
  "thumbs_up_count": 2,
  "thumbs_down_count": 0
}
```

---

## Error Handling

All endpoints return standard HTTP status codes:

| Code | Meaning |
| --- | --- |
| 200 | Success |
| 400 | Bad request (missing field, invalid format) |
| 401 | Unauthorized (missing/invalid API key or user ID) |
| 403 | Forbidden (you don't own this conversation) |
| 404 | Not found (conversation doesn't exist) |
| 500 | Internal server error |

**Error response format:**
```json
{ "detail": "Conversation not found" }
```

---

## Data Model

### Conversation Document (in Cosmos DB)

```json
{
  "id": "abc-123-uuid",
  "client_principal_id": "teacher-12345",
  "created_at": "2026-09-03T10:00:00.000000+00:00",
  "updated_at": "2026-09-03T10:05:30.000000+00:00",
  "questions": [
    {
      "question_id": "q-001",
      "text": "Summarize the 15th century Ottoman Empire",
      "answer": "The Ottoman Empire in the 15th century...",
      "asked_at": "2026-09-03T10:00:00.000000+00:00",
      "answered_at": "2026-09-03T10:00:15.000000+00:00"
    }
  ],
  "feedback": [
    {
      "question_id": "q-001",
      "is_positive": true,
      "stars_rating": 5,
      "feedback_text": "Accurate and concise."
    }
  ]
}
```

**Key points:**
- Partition key = `id` (conversation ID)
- Each question includes the full answer text (persisted at answer time)
- Feedback is stored as-is with optional question and answer joins
- `client_principal_id` scopes all history and feedback queries to one user

---

## Important Notes

### Backfill: No historical data pre-upgrade

Conversations and answers are tracked **from this version forward only**. Conversations created before this upgrade:
- Have no `client_principal_id`, so won't show up in `GET /conversations` for any user
- Can still be accessed directly by ID if you know the UUID
- Have no stored answers

Your backend should track conversation IDs locally if you need to display old history.

### API Key Security

- **Never ship the API key to a browser.** Store it server-side.
- If exposed, regenerate it in Key Vault / App Configuration immediately.
- Rotate it regularly (quarterly recommended).

### Quota & Rate Limiting

No per-user rate limiting is implemented yet. If integrating with thousands of teachers, we should discuss:
- Rate limits (e.g., 100 questions/hour per teacher)
- Token budgets (answers consume tokens)
- Peak load planning

---

## Next: Streaming (Phase 2)

If you want the typewriter UX where answers appear word-by-word, we can add `POST /chat/stream` that returns Server-Sent Events. For now, `POST /chat` with its single JSON response is simpler for most integrations.

---

## Support

Questions or issues? 
- Check `/docs` for interactive Swagger docs
- Check `/openapi.json` for the full OpenAPI schema
- All new endpoints are versioned and can be rolled back separately from `/orchestrator`
