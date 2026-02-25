# Architecture

## How It Works

```
  You run call_manager.py
         │
         ▼
  ┌─────────────┐     dials      ┌──────────────────┐
  │   Twilio     │ ─────────────▶│  Pretty Good AI  │
  │   (phone)    │               │  +1-805-439-8008  │
  └──────┬──────┘               └────────┬─────────┘
         │                               │
    webhooks                        voice (agent speaks)
         │                               │
         ▼                               │
  ┌──────────────────┐                   │
  │  FastAPI Server   │◀─────────────────┘
  │  (main.py)        │
  │                    │
  │  Gather ──▶ GPT-4o ──▶ Say          │
  │  (listen)   (think)    (speak)       │
  │       ◀──── loop ─────┘             │
  └──────────────────┘
```

The system is a Python voice bot that calls Pretty Good AI's test phone number and pretends to be a patient. It's built on **FastAPI** (webhook server), **Twilio** (phone calls), and **GPT-4o** (the patient's brain).

When `call_manager.py` starts a call, Twilio dials the test number and connects to our local server through ngrok. The server tells Twilio to listen using `<Gather input="speech">` — Twilio does real-time speech recognition and sends us the text of what the agent said. We pass that text to GPT-4o along with a scenario prompt (like "you're a patient trying to book on Sunday") and the full conversation history. GPT-4o decides what the patient says next, and we return `<Say>` TwiML so Twilio speaks it back to the agent using a Polly Neural voice. Then we immediately start listening again. This listen → think → speak loop continues until the conversation naturally ends or hits 15 turns. Every call's full transcript gets saved to a text file.

## What Changed During Development

**Version 1 — Record + Whisper + ElevenLabs:**
I initially built the pipeline using Twilio's `<Record>` to capture audio, OpenAI Whisper to transcribe it, GPT-4o to generate the response, and ElevenLabs to synthesize natural-sounding speech. It worked, but the total latency was **8–12 seconds per turn** — downloading the recording, running Whisper, calling GPT-4o, synthesizing audio with ElevenLabs, and serving the file back. During those 8–12 seconds of silence, the agent would interpret the silence and start talking again, causing both AIs to talk over each other.

**Version 2 — Gather + Say (Polly):**
I replaced the entire audio pipeline with Twilio's built-in tools. `<Gather input="speech">` handles speech recognition in real-time (no download, no Whisper), and `<Say>` with a Polly Neural voice handles text-to-speech instantly (no ElevenLabs, no file serving). This cut latency down to **2–3 seconds** — only the GPT-4o call remains as an external API hit.

**Version 3 — Fixing the overlap:**
Even after switching to Gather + Say, both AIs were still talking over each other. The problem was `speechTimeout="auto"` — Twilio's automatic end-of-speech detection was too aggressive. It would interpret any brief natural pause (a breath, a comma) as "they're done talking" and fire off our response while the agent was still mid-sentence. I fixed this by switching to explicit `speechTimeout` values (1–4 seconds depending on the phase of the call) and adding a separate `/handle-silence` endpoint that gracefully handles cases where the agent hasn't spoken yet. The last few calls after this fix sound like natural phone conversations.

## Key Design Choices

- **In-memory state, no database** — calls are short (1–3 min) and sequential, so a Python dict keyed by CallSid is enough. Transcripts are saved to disk.
- **Scenario-driven** — each test case is just a dict in `scenarios.py` with a persona and opening line. Adding a new scenario takes 30 seconds.
- **`[END]` token for hangup** — instead of guessing if the patient said goodbye, GPT-4o explicitly signals when the call should end.
- **Graduated silence handling** — if the agent doesn't speak, we wait silently first, then say "Hello?", then initiate with the scenario's opening line. No premature talking.
