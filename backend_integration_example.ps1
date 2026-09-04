# Sample backend client in PowerShell showing orchestrator API integration
# Run this to test the API and see full examples

# ============================================================================
# Configuration
# ============================================================================

$ORCHESTRATOR_URL = "https://ca-epj2ijiie4drm-orchestrator.purplebay-4a93a1b6.swedencentral.azurecontainerapps.io"
$ORCHESTRATOR_API_KEY = "<your-api-key>"  # Get from Key Vault
$TEACHER_ID = "teacher-uuid-12345"

# Ingestion service (separate deployment, separate API key) - used for document upload
$INGESTION_URL = "https://<ingestion-fqdn>"
$INGESTION_API_KEY = "<your-ingestion-api-key>"  # Get from Key Vault (INGESTION_APP_APIKEY)

# ============================================================================
# Helper function: make API calls with proper headers
# ============================================================================

function Invoke-OrchestratorAPI {
    param(
        [string]$Method = "GET",
        [string]$Path,
        [hashtable]$Body = $null,
        [hashtable]$QueryParams = $null
    )

    $headers = @{
        "X-API-KEY"   = $ORCHESTRATOR_API_KEY
        "X-User-Id"   = $TEACHER_ID
        "Content-Type" = "application/json"
    }

    $uri = "$ORCHESTRATOR_URL$Path"
    if ($QueryParams) {
        $queryString = ($QueryParams.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "&"
        $uri = "$uri`?$queryString"
    }

    $params = @{
        Uri     = $uri
        Method  = $Method
        Headers = $headers
    }

    if ($Body) {
        $params["Body"] = ($Body | ConvertTo-Json -Depth 10)
    }

    try {
        $response = Invoke-WebRequest @params
        $response.Content | ConvertFrom-Json
    }
    catch {
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
        $_.Exception.Response.Content.ToString() | ConvertFrom-Json | Write-Host
        throw
    }
}

# ============================================================================
# Example 1: Ask a question (new conversation)
# ============================================================================

Write-Host "`n=== 1. Ask a question (new conversation) ===" -ForegroundColor Cyan

$question1 = @{
    ask            = "What is the capital of Sweden?"
    conversation_id = $null
    question_id     = "q-001"
} | ConvertTo-Json

$response1 = Invoke-OrchestratorAPI -Method POST -Path "/chat" -Body @{
    ask             = "What is the capital of Sweden?"
    conversation_id = $null
    question_id     = "q-001"
}

Write-Host ($response1 | ConvertTo-Json -Depth 10) -ForegroundColor Green

$conversation_id = $response1.conversation_id
$first_question_id = $response1.question_id


# ============================================================================
# Example 2: Ask a follow-up question (continue conversation)
# ============================================================================

Write-Host "`n=== 2. Ask a follow-up question (continue conversation) ===" -ForegroundColor Cyan

$response2 = Invoke-OrchestratorAPI -Method POST -Path "/chat" -Body @{
    ask             = "Tell me about its history."
    conversation_id = $conversation_id
    question_id     = "q-002"
}

Write-Host ($response2 | ConvertTo-Json -Depth 10) -ForegroundColor Green


# ============================================================================
# Example 3: Submit feedback (thumbs up)
# ============================================================================

Write-Host "`n=== 3. Submit feedback (thumbs up) ===" -ForegroundColor Cyan

$feedback = Invoke-OrchestratorAPI -Method POST -Path "/orchestrator" -Body @{
    type             = "feedback"
    conversation_id  = $conversation_id
    question_id      = $first_question_id
    is_positive      = $true
    stars_rating     = 5
    feedback_text    = "Accurate and concise."
}

Write-Host ($feedback | ConvertTo-Json -Depth 10) -ForegroundColor Green


# ============================================================================
# Example 4: List conversations
# ============================================================================

Write-Host "`n=== 4. List conversations ===" -ForegroundColor Cyan

$conversations = Invoke-OrchestratorAPI -Method GET -Path "/conversations" -QueryParams @{
    limit  = 50
    offset = 0
}

Write-Host ($conversations | ConvertTo-Json -Depth 10) -ForegroundColor Green


# ============================================================================
# Example 5: Get full conversation history
# ============================================================================

Write-Host "`n=== 5. Get full conversation history ===" -ForegroundColor Cyan

$full_history = Invoke-OrchestratorAPI -Method GET -Path "/conversations/$conversation_id"

Write-Host ($full_history | ConvertTo-Json -Depth 10) -ForegroundColor Green


# ============================================================================
# Example 6: Get all feedback for this teacher
# ============================================================================

Write-Host "`n=== 6. Get all feedback (across all conversations) ===" -ForegroundColor Cyan

$all_feedback = Invoke-OrchestratorAPI -Method GET -Path "/feedback" -QueryParams @{
    limit  = 50
    offset = 0
}

Write-Host ($all_feedback | ConvertTo-Json -Depth 10) -ForegroundColor Green


# ============================================================================
# Example 7: Upload a document (ingestion service)
# ============================================================================

Write-Host "`n=== 7. Upload a document ===" -ForegroundColor Cyan

$filePath = "C:\path\to\document.pdf"  # <-- update this to a real file

$uploadHeaders = @{ "X-API-KEY" = $INGESTION_API_KEY }
$form = @{ file = Get-Item -Path $filePath }

$uploadResponse = Invoke-RestMethod -Uri "$INGESTION_URL/documents/upload" `
    -Method Post `
    -Headers $uploadHeaders `
    -Form $form

Write-Host ($uploadResponse | ConvertTo-Json -Depth 10) -ForegroundColor Green

$uploadedFilename = $uploadResponse.filename


# ============================================================================
# Example 8: Query the uploaded document via the orchestrator
# ============================================================================

Write-Host "`n=== 8. Query the uploaded document ===" -ForegroundColor Cyan

$docQueryResponse = Invoke-OrchestratorAPI -Method POST -Path "/chat" -Body @{
    ask             = "Summarize this document"
    uploaded_files  = @($uploadedFilename)
    conversation_id = $null
}

Write-Host ($docQueryResponse | ConvertTo-Json -Depth 10) -ForegroundColor Green

Write-Host "`n✅ All examples completed successfully!" -ForegroundColor Green
