# Orchestrator API — Customer Walkthrough
### Slide-by-slide outline — paste into PowerPoint

---

## Slide 1 — Title
**Orchestrator API for Backend Integration**
Enabling your platform to integrate with our RAG orchestrator

*(Subtitle: Phase 1 — Server-to-Server Integration)*

---

## Slide 2 — Agenda
1. What we built
2. How authentication works (and what you're responsible for)
3. Available endpoints
4. Document upload & query — current state
5. Network exposure options
6. Integration steps
7. What's next (Phase 2 ideas)

---

## Slide 3 — What We Built
- A clean, stable API surface so your backend can talk to our orchestrator
- Non-breaking: your existing integration paths are untouched
- Five new endpoints for asking questions, retrieving history, and feedback
- Full answer text, timestamps, and per-user history now persisted

---

## Slide 4 — Available Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /health` | Health probe (no auth) |
| `POST /chat` | Ask a question, get the full answer back |
| `POST /orchestrator` | Submit thumbs up/down feedback (existing endpoint) |
| `GET /conversations` | List a user's past conversations |
| `GET /conversations/{id}` | Full Q&A history + feedback for one conversation |
| `GET /feedback` | All feedback submitted by a user |

---

## Slide 5 — Authentication Model
**Two headers required on every call (except `/health`):**
- `X-API-KEY` — proves the caller is your backend (shared secret, stored in Key Vault)
- `X-User-Id` — identifies which end-user is asking

**Important — please read carefully:**
> We do **not** validate that `X-User-Id` belongs to a real, authenticated user.
> **Your backend is responsible for authenticating your own end-users** (via your existing login/session system) **before** calling us, and for only ever sending the correct, verified user ID.

Think of it as: *your frontend authenticates the user → your backend calls us on their behalf, server-to-server.* The browser never talks to us directly and never sees the API key.

---

## Slide 6 — Why This Model?
- Simpler and faster to integrate — no need to share our identity provider or validate JWTs from your system
- Your backend already knows who the user is — no duplicate auth logic
- API key blocks all *unauthenticated* traffic from reaching us at all
- Trade-off: security depends on your backend keeping the API key secret and correctly identifying users

*(If you'd prefer we validate user identity tokens directly, that's possible in a future phase — let's discuss your identity provider.)*

---

## Slide 7 — Document Upload & Query — Now Available
- New `POST /documents/upload` endpoint added to the ingestion service — accepts a file, stores it, and indexes it immediately
- Orchestrator's `/chat` accepts an `uploaded_files` list — filters answers to just those files
- Tested end-to-end: upload → index → query → correct, cited answer
- Separate API key from the orchestrator (`INGESTION_APP_APIKEY`), same auth pattern (`X-API-KEY` header)

## Slide 7b — Document Upload: Open Questions (need your input)
- **No per-teacher ownership yet.** Any user could currently reference any uploaded filename — there's no check that a document belongs to the requesting teacher. Do you need strict per-teacher isolation, or is a shared document pool acceptable for your use case?
- **No retention/expiry policy yet.** Files are stored permanently today. Given your use case (e.g., a teacher grading a test may want to reference it again days later), is permanent storage the right model, or do you want automatic cleanup after a period of inactivity?
- **No self-service list/delete.** Teachers can't currently see or remove their own uploaded files — is this needed for launch?

*(These are flagged, not blockers — we can scope and build whichever of these you need.)*

---

## Slide 8 — Network Exposure: Two Options

### Option A — Your backend is in Azure
✅ **VNet Peering**
- No public internet exposure — most secure
- Requires your Azure VNet to peer with ours
- Best if your infrastructure is already in Azure

### Option B — Your backend is outside Azure (on-prem, another cloud, etc.)
✅ **Application Gateway**
- Public IP + Web Application Firewall in front of the orchestrator
- Orchestrator itself stays internal; App Gateway is the only public entry point
- Still fully protected by the API key — publicly reachable ≠ unauthenticated

**Question for you:** Where does your backend run today?

---

## Slide 9 — Integration Steps (Your Team)
1. Authenticate your end-user as normal (your existing login system)
2. Call `POST /chat` with `X-API-KEY` + `X-User-Id`, get back `conversation_id`, `question_id`, `answer`
3. Store those IDs if you want follow-up questions or feedback later
4. Call `POST /orchestrator` (feedback type) when a user clicks 👍/👎
5. Call `GET /conversations` / `GET /conversations/{id}` to show history in your UI

*(Sample code provided in Python and PowerShell — ready to adapt.)*

---

## Slide 10 — What's Not Included Yet (Optional Future Work)
- **Streaming answers** (typewriter-style, word-by-word) — currently `/chat` returns the full answer at once
- **Rate limiting** — no per-user quotas yet; can be added if you expect high volume
- **Direct user-token validation** — currently trust-based via your backend
- **Document upload integration** — separate project against the ingestion service

---

## Slide 11 — Summary
- ✅ Phase 1 API is built, tested, and deployed
- ✅ Full conversation history, answers, and feedback now tracked per user
- ✅ Secured by API key; network exposure path depends on where you host
- 🤝 Your team owns end-user authentication; we own the orchestrator's data and reasoning

---

## Slide 12 — Questions / Discussion
- Where is your backend hosted? (decides VNet peering vs. Application Gateway)
- Do you need streaming responses?
- Do you need end-user document uploads?
- What's your expected request volume? (informs rate limiting)
