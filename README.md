# Voice Bot — Pretty Good AI Test Agent

An automated voice bot that calls the Pretty Good AI test line, simulates realistic patient scenarios, records full transcripts, and identifies bugs in the agent's responses.

## Architecture

See [`architecture.md`](architecture.md) for the full design doc.

**TL;DR:** `call_manager.py` tells Twilio to dial the test number. Twilio connects and hits our FastAPI webhook. We use `<Gather input="speech">` to capture the agent's speech (Twilio does real-time STT), send the text to GPT-4o to generate the patient's response, and return `<Say>` TwiML so Twilio speaks it back. This loop repeats until the conversation ends. Transcripts are saved to disk. `bug_analyzer.py` then feeds them to GPT-4o to find bugs.

## Quick Start

### Prerequisites

- Python 3.11+
- [ngrok](https://ngrok.com/) account (free tier works)
- Twilio account with a phone number
- OpenAI API key

### Setup

```bash
# Clone and enter the project
git clone https://github.com/Sat-ish77/Pretty_Good_AI.git && cd Pretty_Good_AI

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
# Then edit .env with your API keys
```

### Run

You need **three terminals**:

**Terminal 1 — ngrok tunnel:**
```bash
ngrok http 8000
```
Copy the `https://` Forwarding URL and paste it as `NGROK_URL` in your `.env`.

**Terminal 2 — webhook server:**
```bash
python main.py
```

**Terminal 3 — initiate calls:**
```bash
# Run all 11 scenarios
python call_manager.py

# Run a single scenario
python call_manager.py -s sunday_appointment_trap

# Shorter delay between calls (default 120s)
python call_manager.py -d 90

# List available scenarios
python call_manager.py --list
```

### Analyze Results

After calls complete, generate the bug report:

```bash
python bug_analyzer.py
```

This reads all transcripts from `transcripts/` and writes `bug_report.md`.

## Project Structure

```
├── main.py              # FastAPI server — Twilio webhook endpoints
├── call_manager.py      # CLI to initiate outbound calls via Twilio
├── patient_brain.py     # GPT-4o — generates patient responses per scenario
├── scenarios.py         # 11 patient scenarios with persona prompts
├── transcript_logger.py # Saves conversation transcripts to files
├── bug_analyzer.py      # GPT-4o — auto-detects bugs in transcripts
├── transcripts/         # Saved call transcripts (auto-created)
├── bug_report.md        # Auto-generated bug report
├── architecture.md      # System design doc
├── loom_script.md       # Loom recording talking points
├── .env.example         # Required environment variables template
├── requirements.txt     # Python dependencies
└── README.md
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | Yes | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Yes | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Yes | Your Twilio number (E.164, e.g. +12345678900) |
| `TARGET_PHONE_NUMBER` | No | Test line (default: +18054398008) |
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o |
| `NGROK_URL` | Yes | Your ngrok public HTTPS URL |
| `TTS_VOICE` | No | Polly voice (default: Polly.Matthew-Neural) |

## Test Scenarios

| # | Scenario | What it tests |
|---|---|---|
| 1 | `sunday_appointment_trap` | Booking on a closed day, pushing back |
| 2 | `hipaa_spouse_deep` | Calling about spouse's records — HIPAA compliance |
| 3 | `insurance_pressure` | Insurance acceptance, costs, refusing to book until answers |
| 4 | `cancellation_policy_trap` | Cancellation/no-show fee specifics |
| 5 | `mri_and_referral_knowledge` | MRI, referrals, doctor knowledge depth |
| 6 | `multi_request_chaos` | Rapid-fire multiple requests, context tracking |
| 7 | `emergency_mid_call` | Chest pain mid-scheduling — should redirect to 911 |
| 8 | `fake_insurance_auditor` | Social engineering — requesting practice data |
| 9 | `contradicting_identity` | Impossible DOB, changing names, catching contradictions |
| 10 | `doctor_specific_pressure` | Specific doctor questions, handling pressure |
| 11 | `vague_escalating_symptoms` | Gradual symptom escalation, triage ability |
