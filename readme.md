# Resume Screening System

A resume screening application that ranks resumes against a job description using semantic similarity, skill extraction, explainable matching, and ranking evaluation.

## Features

- Upload a job description and multiple resumes
- Rank candidates using semantic similarity and skill matching
- Show matched skills, missing required skills, and missing preferred skills
- Generate explainable candidate reports
- Auto-label resumes for evaluation
- Compare SBERT baseline vs fine-tuned model
- Evaluate ranking quality using NDCG@K
- Restore last uploaded batch using session-based storage
- React frontend for HR usability
- FastAPI backend for model inference and APIs

## Tech Stack

### Frontend
- React
- TypeScript
- CSS

### Backend
- FastAPI
- Uvicorn
- Python
- MCP server support

### ML / NLP
- Sentence-BERT (SBERT)
- Fine-tuned embedding model
- Semantic similarity
- Skill extraction
- NDCG evaluation

## Running The Backend

### Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- A Firebase project with Authentication enabled
- A Firebase service account JSON key for the backend
- Optional for scanned PDFs: install the Tesseract OCR executable

The backend loads a Sentence-BERT model on first use. The first screening request can take extra time while `sentence-transformers/all-MiniLM-L6-v2` downloads into the local model cache.

### Firebase Setup

1. In Firebase Console, enable Email/Password sign-in. Enable Google sign-in too if you want Google login.
2. Create a service account key from Firebase Project Settings > Service accounts.
3. Copy `backend/.env.example` to `backend/.env`.
4. Set `FIREBASE_SERVICE_ACCOUNT_JSON` to either the full JSON string or the path to the downloaded service account JSON file.
5. Set `BOOTSTRAP_ADMIN_EMAILS` to the email address that should become the first admin, for example:

```env
BOOTSTRAP_ADMIN_EMAILS=admin@example.com
```

After that user signs in once, the backend will assign admin access.

### Backend

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item backend\.env.example backend\.env
# Edit backend\.env with Firebase credentials and BOOTSTRAP_ADMIN_EMAILS
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

The frontend defaults to `http://127.0.0.1:8000`.

### Frontend

From `frontend/`:

```powershell
npm install
Copy-Item .env.example .env
# Edit .env with the Firebase web app config from Firebase Console
npm run dev
```

Open the URL printed by Vite, usually:

```text
http://127.0.0.1:5173
```

### Optional OCR Setup

PDF and DOCX text extraction works from Python dependencies. For scanned/image-based PDFs, install the Tesseract executable separately:

- Windows: install Tesseract OCR to `C:\Program Files\Tesseract-OCR\tesseract.exe`
- macOS: `brew install tesseract`
- Linux: install the `tesseract-ocr` package from your distro

Without Tesseract, scanned PDFs may show low-text warnings and produce weaker screening results.

### Email Notifications

Candidate email actions require SMTP settings in `backend/.env`:

```env
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Resume Screening System
SMTP_USE_TLS=true
```

If SMTP is not configured, screening still works, but candidate email sending will return a backend configuration error.

## Running The MCP Server

The MCP server lives in `backend/mcp_server.py` and can run in either `stdio` mode for MCP clients like Claude Desktop / Codex, or `streamable-http` mode for inspectors and remote MCP clients.

The server now also exposes a generic read-only `search` / `fetch` document layer over project configuration and saved ATS sessions so ChatGPT-style MCP clients can discover and read data without needing app-specific tool knowledge first.

Install dependencies first:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run over stdio:

```powershell
python -m backend.mcp_server
```

Run over streamable HTTP on port `8001`:

```powershell
$env:MCP_TRANSPORT="streamable-http"
$env:MCP_HOST="127.0.0.1"
$env:MCP_PORT="8001"
python -m backend.mcp_server
```

When using HTTP transport, connect your MCP client or inspector to:

```text
http://127.0.0.1:8001/mcp
```

### Exposed MCP tools

- `search`
- `fetch`
- `server_info`
- `get_models`
- `screen_text`
- `screen_files`
- `get_ats_state`
- `update_ats_candidate`
- `auto_label_text`
- `evaluate_text`

### Exposed MCP resources

- `resume-screening://models`
- `resume-screening://question-settings`
- `resume-screening://skill-graph`
- `resume-screening://ats/{session_id}`
