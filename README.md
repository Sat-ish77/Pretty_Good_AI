# Voice Bot — Pretty Good AI Test Agent

An automated voice bot that calls the Pretty Good AI test line, simulates realistic patient scenarios, records full transcripts, and identifies bugs in the agent's responses.

## Architecture

See [`architecture.md`](architecture.md) for the full design doc.

**TL;DR:** `call_manager.py` tells Twilio to dial the test number. Twilio connects and hits our FastAPI webhook. We use `<Gather input="speech">` to capture the agent's speech (Twilio does real-time STT), send the text to GPT-4o-mini to generate the patient's response, and immediately play a pre-generated filler sound while ElevenLabs synthesizes the real audio in the background. This loop repeats until the conversation ends. Transcripts are saved to disk, then reviewed for bugs.

## Quick Start

### Prerequisites

- Python 3.11+


# Pretty Good AI — Voice Bot Test Agent

Pretty Good AI is an automated voice bot platform designed to simulate realistic patient scenarios, interact with a test phone line, and evaluate conversational AI agents. The system records full transcripts and helps identify bugs or compliance issues in agent responses.

## Overview

This project leverages Twilio for telephony, FastAPI for webhooks, OpenAI for patient simulation, and ElevenLabs for high-quality speech synthesis. It is ideal for testing, benchmarking, and improving healthcare conversational agents.

## Features

- Automated outbound calls to a test line
- Realistic patient scenario simulation using GPT-4o-mini
- Real-time speech-to-text and TTS integration
- Full transcript logging for review and analysis
- Modular scenario and persona system

## Getting Started

### Prerequisites

- Python 3.11+
- [ngrok](https://ngrok.com/) account
- Twilio account with a phone number
- OpenAI API key
- ElevenLabs API key

### Installation

```bash
git clone https://github.com/Sat-ish77/Pretty_Good_AI.git
cd Pretty_Good_AI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API keys
```

### Running the System

1. **Start ngrok**
	```bash
	ngrok http 8000
	```
	Copy the HTTPS forwarding URL to your `.env` as `NGROK_URL`.

2. **Launch the webhook server**
	```bash
	python main.py
	```

3. **Initiate calls**
	```bash
	python call_manager.py
	# or run a specific scenario
	python call_manager.py -s sunday_appointment_trap
	# or list all scenarios
	python call_manager.py --list
	```

## Project Structure

```
main.py               # FastAPI server — Twilio webhook endpoints
call_manager.py       # CLI to initiate outbound calls via Twilio
patient_brain.py      # GPT-4o-mini — patient response generation
voice_synthesizer.py  # ElevenLabs TTS — patient audio synthesis
scenarios.py          # Patient scenarios and personas
transcript_logger.py  # Transcript saving utility
transcripts/          # Saved call transcripts
audio_cache/          # Pre-generated and per-turn audio
bug_report.md         # Known bugs and issues
architecture.md       # System design document
.env.example          # Environment variable template
requirements.txt      # Python dependencies
README.md             # Project documentation
```

## Configuration

Set the following environment variables in your `.env` file:

| Variable               | Required | Description                                      |
|------------------------|----------|--------------------------------------------------|
| TWILIO_ACCOUNT_SID     | Yes      | Twilio account SID                               |
| TWILIO_AUTH_TOKEN      | Yes      | Twilio auth token                                |
| TWILIO_PHONE_NUMBER    | Yes      | Your Twilio number (E.164, e.g. +12345678900)    |
| TARGET_PHONE_NUMBER    | No       | Test line (default: +18054398008)                |
| OPENAI_API_KEY         | Yes      | OpenAI API key for GPT-4o-mini                   |
| ELEVENLABS_API_KEY     | Yes      | ElevenLabs API key for TTS                       |
| ELEVENLABS_VOICE_ID    | Yes      | ElevenLabs voice ID                              |
| NGROK_URL              | Yes      | Your ngrok public HTTPS URL                      |
| TTS_VOICE              | No       | Polly fallback voice (default: Polly.Matthew-Neural) |

## Test Scenarios

| #  | Scenario                    | Description                                      |
|----|-----------------------------|--------------------------------------------------|
| 1  | sunday_appointment_trap     | Booking on a closed day, pushing back            |
| 2  | hipaa_spouse_deep           | HIPAA compliance for spouse's records            |
| 3  | insurance_pressure          | Insurance acceptance, costs, booking resistance  |
| 4  | cancellation_policy_trap    | Cancellation/no-show fee specifics               |
| 5  | mri_and_referral_knowledge  | MRI, referrals, doctor knowledge depth           |
| 6  | multi_request_chaos         | Rapid-fire requests, context tracking            |
| 7  | emergency_mid_call          | Emergency during scheduling, 911 redirection     |
| 8  | fake_insurance_auditor      | Social engineering, practice data requests       |
| 9  | contradicting_identity      | Impossible DOB, changing names, contradictions   |
| 10 | doctor_specific_pressure    | Specific doctor questions, handling pressure     |
| 11 | vague_escalating_symptoms   | Gradual symptom escalation, triage ability       |

## Contributing

Contributions are welcome! To propose improvements, bug fixes, or new scenarios:

1. Fork the repository and create a feature branch.
2. Make your changes (documentation, scenarios, tests, etc.).
3. Ensure all existing checks pass.
4. Submit a pull request with a clear description of your changes.

Ideas for contribution:
- Add new patient scenarios or personas
- Improve documentation or setup instructions
- Enhance test coverage or add health-check endpoints
- Report or fix bugs in the call flow

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.


