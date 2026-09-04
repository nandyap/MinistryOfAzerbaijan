"""
Sample backend client showing how to integrate with the orchestrator API.

This demonstrates the server-to-server pattern where a teacher's platform
backend calls the orchestrator API, not the browser.

Usage:
    python -m pip install httpx
    python backend_sample.py
"""

import json
from typing import Optional
import httpx

# ============================================================================
# Configuration
# ============================================================================

ORCHESTRATOR_URL = "https://ca-epj2ijiie4drm-orchestrator.purplebay-4a93a1b6.swedencentral.azurecontainerapps.io"
ORCHESTRATOR_API_KEY = "<your-api-key>"  # Get from Key Vault or App Configuration

# Example teacher ID (your platform provides this)
TEACHER_ID = "teacher-uuid-12345"

# Ingestion service (separate deployment, separate API key) - used for document upload
INGESTION_URL = "https://<ingestion-fqdn>"
INGESTION_API_KEY = "<your-ingestion-api-key>"  # Get from Key Vault (INGESTION_APP_APIKEY)


# ============================================================================
# API Client
# ============================================================================

class OrchestratorClient:
    """
    Synchronous client for the orchestrator API.
    Use httpx.AsyncClient if you need async.
    """

    def __init__(self, base_url: str, api_key: str, teacher_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.teacher_id = teacher_id
        self.client = httpx.Client(timeout=30.0, verify=False)  # verify=False for self-signed certs in dev

    def _headers(self) -> dict:
        """Common headers for all requests."""
        return {
            "X-API-KEY": self.api_key,
            "X-User-Id": self.teacher_id,
            "Content-Type": "application/json",
        }

    def ask(self, question: str, conversation_id: Optional[str] = None, question_id: Optional[str] = None) -> dict:
        """
        Ask a question and get an answer back as JSON.

        Args:
            question: The question text
            conversation_id: Continue an existing conversation (or None for new)
            question_id: Unique ID for this question (or None to auto-generate)

        Returns:
            {"conversation_id": "...", "question_id": "...", "answer": "...", "timestamp": "..."}
        """
        payload = {
            "ask": question,
            "conversation_id": conversation_id,
            "question_id": question_id,
        }
        response = self.client.post(
            f"{self.base_url}/chat",
            json=payload,
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def submit_feedback(
        self,
        conversation_id: str,
        question_id: str,
        is_positive: Optional[bool] = None,
        stars_rating: Optional[int] = None,
        feedback_text: Optional[str] = None,
    ) -> dict:
        """
        Submit thumbs up/down feedback on a specific answer.

        Args:
            conversation_id: Which conversation
            question_id: Which question in that conversation
            is_positive: True = 👍, False = 👎, None = skip
            stars_rating: 1-5, optional
            feedback_text: Free-form comment, optional

        Returns:
            {"status": "success", "message": "Feedback saved successfully"}
        """
        payload = {
            "type": "feedback",
            "conversation_id": conversation_id,
            "question_id": question_id,
            "is_positive": is_positive,
            "stars_rating": stars_rating,
            "feedback_text": feedback_text,
        }
        response = self.client.post(
            f"{self.base_url}/orchestrator",  # Feedback goes to /orchestrator, not /chat
            json=payload,
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def list_conversations(self, limit: int = 50, offset: int = 0) -> dict:
        """
        Get conversation summaries for this teacher.

        Args:
            limit: How many to return (1-200)
            offset: Pagination offset

        Returns:
            {
                "conversations": [
                    {
                        "conversation_id": "...",
                        "created_at": "...",
                        "question_count": 3,
                        "thumbs_up_count": 2,
                        "thumbs_down_count": 0,
                        "first_question": "What is...",
                        ...
                    }
                ],
                "count": 1
            }
        """
        response = self.client.get(
            f"{self.base_url}/conversations",
            params={"limit": limit, "offset": offset},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def get_conversation(self, conversation_id: str) -> dict:
        """
        Get full history for one conversation (all Q&A turns + all feedback).

        Args:
            conversation_id: The conversation to retrieve

        Returns:
            {
                "conversation_id": "...",
                "questions": [
                    {
                        "question_id": "...",
                        "text": "...",
                        "answer": "...",
                        "asked_at": "...",
                        "answered_at": "..."
                    }
                ],
                "feedback": [
                    {
                        "question_id": "...",
                        "is_positive": true,
                        "stars_rating": 5,
                        "feedback_text": "...",
                        "question_text": "...",
                        "answer": "..."
                    }
                ]
            }
        """
        response = self.client.get(
            f"{self.base_url}/conversations/{conversation_id}",
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def get_feedback(self, limit: int = 50, offset: int = 0) -> dict:
        """
        Get all feedback given by this teacher (across all conversations).

        Useful for analytics: "What % of answers were rated positively?"

        Args:
            limit: How many conversations to scan (pagination limit)
            offset: Pagination offset

        Returns:
            {
                "feedback": [...],  # All feedback entries across all conversations
                "count": 12,
                "thumbs_up_count": 9,
                "thumbs_down_count": 3
            }
        """
        response = self.client.get(
            f"{self.base_url}/feedback",
            params={"limit": limit, "offset": offset},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the HTTP connection pool."""
        self.client.close()


# ============================================================================
# Ingestion Client (document upload - separate service, separate API key)
# ============================================================================

class IngestionClient:
    """
    Client for the ingestion service's document upload endpoint.

    This is a different Container App from the orchestrator, with its own
    FQDN and its own API key (INGESTION_APP_APIKEY). Uploaded files are
    indexed immediately and can then be referenced via `uploaded_files`
    when calling OrchestratorClient.ask().
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(timeout=120.0, verify=False)  # longer timeout: upload + indexing

    def upload_document(self, file_path: str) -> dict:
        """
        Upload a document and trigger indexing immediately.

        Args:
            file_path: Local path to the file (.pdf, .docx, .pptx, .txt, .md,
                       .html, .csv, .xlsx, etc.)

        Returns:
            {"status": "uploaded", "filename": "...", "container": "documents",
             "indexing_status": "completed"}

        Note: The returned `filename` is what you pass into
        OrchestratorClient.ask(..., uploaded_files=[filename]) to scope
        answers to this document.
        """
        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1].split("\\")[-1], f)}
            response = self.client.post(
                f"{self.base_url}/documents/upload",
                files=files,
                headers={"X-API-KEY": self.api_key},
            )
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the HTTP connection pool."""
        self.client.close()


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    client = OrchestratorClient(ORCHESTRATOR_URL, ORCHESTRATOR_API_KEY, TEACHER_ID)

    try:
        # 1. Ask a question (starts a new conversation)
        print("\n1. Asking a question...")
        response = client.ask(
            question="What is the capital of Sweden?",
            question_id="q-001",
        )
        print(json.dumps(response, indent=2))

        conversation_id = response["conversation_id"]
        question_id = response["question_id"]

        # 2. Ask a follow-up question (continue the conversation)
        print("\n2. Asking a follow-up question...")
        response2 = client.ask(
            question="Tell me about its history.",
            conversation_id=conversation_id,
            question_id="q-002",
        )
        print(json.dumps(response2, indent=2))

        # 3. Submit thumbs-up feedback on the first answer
        print("\n3. Submitting feedback...")
        feedback_response = client.submit_feedback(
            conversation_id=conversation_id,
            question_id=question_id,
            is_positive=True,
            stars_rating=5,
            feedback_text="Accurate and concise.",
        )
        print(json.dumps(feedback_response, indent=2))

        # 4. List all conversations for this teacher
        print("\n4. Listing conversations...")
        convs = client.list_conversations(limit=50)
        print(json.dumps(convs, indent=2))

        # 5. Get full history for one conversation
        print("\n5. Getting full conversation history...")
        full_conv = client.get_conversation(conversation_id)
        print(json.dumps(full_conv, indent=2))

        # 6. Get all feedback for this teacher
        print("\n6. Getting all feedback...")
        all_feedback = client.get_feedback(limit=50)
        print(json.dumps(all_feedback, indent=2))

        # 7. Upload a document and query it (ingestion service)
        print("\n7. Uploading a document...")
        ingestion_client = IngestionClient(INGESTION_URL, INGESTION_API_KEY)
        try:
            upload_response = ingestion_client.upload_document("C:/path/to/document.pdf")
            print(json.dumps(upload_response, indent=2))

            uploaded_filename = upload_response["filename"]

            print("\n8. Querying the uploaded document...")
            doc_response = client.client.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"ask": "Summarize this document", "uploaded_files": [uploaded_filename]},
                headers=client._headers(),
            )
            doc_response.raise_for_status()
            print(json.dumps(doc_response.json(), indent=2))
        finally:
            ingestion_client.close()

    except httpx.HTTPError as e:
        print(f"Error: {e}")
    finally:
        client.close()


# ============================================================================
# Integration Examples for Your Platform
# ============================================================================

"""
How to integrate this into your teacher platform:

1. When a teacher asks a question in your UI:
   - Call orchestrator.ask(question)
   - Display the answer returned in response["answer"]
   - Store response["conversation_id"] locally (or show it to the teacher)
   - Store response["question_id"] for when they rate it

2. When a teacher clicks 👍 or 👎:
   - Call orchestrator.submit_feedback(conversation_id, question_id, is_positive=True/False)
   - Show "Thanks for your feedback!"

3. Add a "My Conversations" section to your platform:
   - Call orchestrator.list_conversations()
   - Display as a list sorted by most recent
   - Click one to open it

4. Open a conversation:
   - Call orchestrator.get_conversation(conversation_id)
   - Display the full Q&A history
   - Show feedback if present

5. Add analytics dashboard:
   - Call orchestrator.get_feedback()
   - Display "👍 {thumbs_up_count} · 👎 {thumbs_down_count}"
   - Calculate % positive = thumbs_up / (thumbs_up + thumbs_down) * 100

6. Error handling:
   - 401: Invalid API key or missing X-User-Id header
   - 403: Teacher trying to access another teacher's conversation
   - 404: Conversation doesn't exist (ID typo?)
   - 500: Orchestrator error (transient, retry)
"""
