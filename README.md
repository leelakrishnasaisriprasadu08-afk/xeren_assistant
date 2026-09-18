# Xeren Assistant — Phase 1 Core

> **Your Personal AI Automation Assistant**  
> *Build Today • Power Xeren Tomorrow*

---

## 🏛️ Phase 1 Architecture

```
User ──► Intent ──► Planner ──► Controller ──► Permission Gate ──► Tool Registry ──► Execution ──► Trust Boundary ──► Verifier ──► Response ──► Trace & Memory
```

### Key Highlights
- **Strict Security Gate**: Operation-level permissions (`ALLOWED`, `ASK`, `DENIED`). Deletions are hard-blocked in Phase 1.
- **Deterministic Path Containment**: Resolves all file access inside `workspace_root`, strictly defeating path traversal attacks.
- **Trust Boundary Layer**: Treats all external web/GitHub data as untrusted with zero instruction authority.
- **Secret Isolation**: In-memory secret store with automatic redaction from all logs and traces.
- **Bounded Controller**: Capped at 10 max steps, max 2 retries on verification failure, per-tool timeout, overall timeout, and cancellation token support.
- **Deterministic Verification**: Validates structure, schemas, and return sanity before returning responses.

---

## 🚀 Quickstart

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Configuration
Copy `.env.example` to `.env` and add your keys:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
GITHUB_TOKEN=your_optional_github_token_here
```

### 3. Interactive CLI
```bash
python main.py cli
```

### 4. REST API Server
```bash
python main.py api --port 8000
```
- Open `http://127.0.0.1:8000/docs` for interactive Swagger documentation.

### 5. One-Shot Query
```bash
python main.py run "read file README.md"
```

---

## 🧪 Running Acceptance Tests

Run the complete Phase-1 acceptance test suite across unit, integration, and security boundaries:

```bash
pytest
```
