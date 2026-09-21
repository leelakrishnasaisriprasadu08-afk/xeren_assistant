# Xeren Assistant — Autonomous Enterprise AI & Linux Security

> **Your Personal Autonomous Multimodal AI & Voice Assistant**  
> *Embodied Automation • Linux-Grade Ring 0 Security • Real-time Voice Studio • Web Builder*

---

## 🏛️ Comprehensive Architecture

```
User Voice / Text ──► Speech Recognition (STT) ──► Intent Classifier ──► DAG Task Planner ──► Execution Controller
                                                                                                    │
               ┌────────────────────────────────────────────────────────────────────────────────────┤
               ▼                                                    ▼                               ▼
       [Security Rings 0-3]                                [Multimodal Engine]              [Voice Engine (TTS)]
   • AES-256 Vault Enclave                              • Vision Screen Analysis         • Windows SAPI Synth
   • Single-Use Credential Leases                       • Browser Automation / Scraping  • Web Speech API Bridge
   • SHA256 Chained Audit Logs                          • AST Codebase Index & Patch     • Dual-Loop Verifier
```

### Key Highlights
- **🎙️ Real-time Voice Assistant**:
  - **Speech-to-Text (STT)**: Instant push-to-talk microphone button (`🎙️`) with real-time speech recognition and glowing sound wave visualizer.
  - **Text-to-Speech (TTS)**: Dual audio engine with native Windows SAPI PowerShell speech synthesis + zero-latency Web Speech `SpeechSynthesis` bridge.
  - **Voice Mode**: Automatic vocal response reading with clean markdown stripping and voice profile customization.
- **🛡️ Linux-Grade Security Rings (0–3)**:
  - **Ring 0 (Hardware/Crypto Enclave)**: AES-256 PBKDF2 vault, encrypted platform credentials (LinkedIn, Upwork, Gmail, GitHub), 60-second ephemeral leases, and real-time 2FA/OTP code handling.
  - **Ring 1 (Core Policy Gate)**: Tamper-evident SHA-256 audit chaining and human-in-the-loop permission gating.
  - **Ring 2 (Tool Sandbox)**: Isolated subprocess execution, AST code indexing, and terminal sandboxing.
  - **Ring 3 (User Space / Masked Telemetry)**: Real-time UI metrics, masked passwords, and flamegraphs.
- **🚀 Autonomous Web Builder & Servers**:
  - Scaffolds complete HTML5/CSS3/JS responsive web apps from natural language prompts.
  - Background HTTP live preview servers with instant launch and status controls.
- **⚡ Deterministic DAG Pipeline & Dual-Loop Verification**:
  - Topological waves, dependency resolution, self-healing replanning, and semantic response verification.

---

## 🚀 Quickstart

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Configuration
Copy `.env.example` to `.env` and add your optional keys:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
GITHUB_TOKEN=your_optional_github_token_here
```

### 3. Interactive Web Dashboard & REST API
```bash
python main.py api --port 8000
```
- Open `http://127.0.0.1:8000/` for the interactive Xeren Web Dashboard with Voice Assistant, Security Vault, and Web Builder.
- Open `http://127.0.0.1:8000/docs` for interactive Swagger API documentation.

### 4. Interactive Voice & Command CLI
```bash
python main.py cli
```

### 5. One-Shot Query / Speech
```bash
python main.py run "speak all systems operational out loud"
```

---

## 🧪 Running Acceptance Tests

Run the complete test suite across unit, integration, voice workflows, and security boundaries:

```bash
pytest -v
```
*(160 passing tests across all modules)*

