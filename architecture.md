# Architecture

## How It Works

```
call_manager.py --> Twilio --> Pretty Good AI (+1-805-439-8008)
                                      |
                                 agent speaks
                                      |
                               FastAPI (main.py)
                                      |
                    Twilio STT --> agent text captured
                                      |
                          filler plays instantly (from disk)
                                      |
                    background --> GPT-4o-mini --> ElevenLabs --> play response
                                      |
                                   loop back
```

The system is a Python voice bot that calls Pretty Good AI's test phone number and pretends to be a patient. It's built on **FastAPI** (webhook server), **Twilio** (phone calls), **GPT-4o-mini** (the patient's brain), and **ElevenLabs** (natural-sounding voice).

When `call_manager.py` starts a call, Twilio dials the test number and connects to our local server through ngrok. The server tells Twilio to listen using `<Gather input="speech">` — Twilio does real-time speech recognition and sends us the text of what the agent said. We pass that text to GPT-4o-mini along with a scenario prompt (like "you're a patient trying to book on Sunday") and the full conversation history. GPT-4o-mini decides what the patient says next. Rather than waiting for synthesis to complete, we immediately return a pre-generated filler sound ("Mmmm..", "Okayyy...") so the caller never hears silence, while GPT-4o-mini and ElevenLabs run as a background asyncio task. Twilio polls `/get-response` until the real response is ready, then plays it back. This listen → think → speak loop continues until the conversation naturally ends or hits 15 turns. Every call's full transcript gets saved to a text file.

---

## What Changed During Development

**Version 1 — Record + Whisper + ElevenLabs:**
I initially built the pipeline using Twilio's `<Record>` to capture audio, OpenAI Whisper to transcribe it, GPT-4o-mini to generate the response, and ElevenLabs to synthesize natural-sounding speech. It worked, but the total latency was **8–12 seconds per turn** — downloading the recording, running Whisper, calling GPT-4o-mini, synthesizing audio with ElevenLabs, and serving the file back. During those 8–12 seconds of silence, the agent would interpret the silence and start talking again, causing both AIs to talk over each other.

**Version 2 — Gather + Say (Polly):**
I replaced the entire audio pipeline with Twilio's built-in tools. `<Gather input="speech">` handles speech recognition in real-time (no download, no Whisper), and `<Say>` with a Polly Neural voice handles text-to-speech instantly (no ElevenLabs, no file serving). This cut latency down to **2–3 seconds** — only the GPT-4o-mini call remains as an external API hit.

**Version 3 — Fixing the overlap:**
Even after switching to Gather + Say, both AIs were still talking over each other. The problem was `speechTimeout="auto"` — Twilio's automatic end-of-speech detection was too aggressive. It would interpret any brief natural pause (a breath, a comma) as "they're done talking" and fire off our response while the agent was still mid-sentence. I fixed this by switching to explicit `speechTimeout` values (1–4 seconds depending on the phase of the call) and adding a separate `/handle-silence` endpoint that gracefully handles cases where the agent hasn't spoken yet.

**Version 4 — Two-phase redirect + ElevenLabs + smart fillers:**
Switched back to ElevenLabs for natural voice quality — Polly sounded robotic compared to what a real patient would sound like. To solve the latency ElevenLabs introduced (1–2s per synthesis), implemented a two-phase architecture: when the agent finishes speaking, we immediately return a pre-generated filler sound from disk (zero latency), while GPT-4o-mini and ElevenLabs run as a background asyncio task. Twilio redirects to `/get-response` which polls until the background task completes, then plays the real response. Added several supporting improvements: OpenAI warmup call at startup to eliminate the cold-start penalty on Turn 1, context-aware filler selection based on what the agent just said (e.g. "Okayyy..." for name/DOB questions, "Mmmm.." for general responses), and no-repeat logic so the same filler never plays twice in a row. Final average latency: **2.5–3 seconds per turn**, with the caller hearing a natural filler sound immediately.

---

## Key Design Choices

- **In-memory state, no database** — calls are short (1–3 min) and sequential, so a Python dict keyed by CallSid is enough. Transcripts are saved to disk.
- **Scenario-driven** — each test case is just a dict in `scenarios.py` with a persona and opening line. Adding a new scenario takes 30 seconds.
- **`[END]` token for hangup** — instead of guessing if the patient said goodbye, GPT-4o-mini explicitly signals when the call should end by appending `[END]` to its response.
- **Graduated silence handling** — if the agent doesn't speak, we wait silently first, then say "Hello?", then initiate with the scenario's opening line. No premature talking.
- **Pre-generated fillers + warmup** — all filler audio files are synthesized at startup so they're served instantly during calls. A dummy OpenAI call at startup eliminates the cold-start penalty that was causing 5+ second delays on Turn 1.
- **Polly fallback** — if ElevenLabs fails or runs out of credits mid-call, the bot automatically falls back to Polly Neural voice so calls complete rather than dropping.
