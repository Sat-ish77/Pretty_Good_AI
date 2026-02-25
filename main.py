from dotenv import load_dotenv
load_dotenv()

import os
import logging
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse

from scenarios import SCENARIOS
from patient_brain import get_patient_response
from transcript_logger import TranscriptLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("voicebot")

app = FastAPI(title="Voice Bot — Pretty Good AI Tester")

NGROK_URL = os.getenv("NGROK_URL", "").rstrip("/")
MAX_TURNS = 15
VOICE = os.getenv("TTS_VOICE", "Polly.Matthew-Neural")

conversations: dict[str, dict] = {}

os.makedirs("transcripts", exist_ok=True)


def _twiml(vr: VoiceResponse) -> Response:
    return Response(content=str(vr), media_type="application/xml")


def _gather(vr: VoiceResponse, timeout: int = 12, speech_timeout: int = 1):
    """Append a <Gather> that waits for the agent to fully finish speaking.

    speech_timeout is seconds of silence after speech before Twilio considers
    the utterance complete. Higher = more patient (won't cut mid-sentence),
    lower = more responsive. Tuned per-call-phase via the callers below.
    """
    vr.gather(
        input="speech",
        action="/handle-response",
        speech_timeout=str(speech_timeout),
        timeout=timeout,
        language="en-US",
    )


# ── Webhooks ────────────────────────────────────────────────────────────

@app.post("/voice")
async def voice_webhook(request: Request):
    """Twilio hits this when the outbound call connects."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    scenario_name = request.query_params.get("scenario", SCENARIOS[0]["name"])

    scenario = next(
        (s for s in SCENARIOS if s["name"] == scenario_name),
        SCENARIOS[0],
    )

    conversations[call_sid] = {
        "scenario": scenario,
        "history": [],
        "turns": 0,
        "silence_count": 0,
        "logger": TranscriptLogger(scenario["name"], call_sid),
        "start_time": datetime.now(),
    }

    logger.info("CALL STARTED  sid=%s  scenario=%s", call_sid, scenario["name"])

    # Just listen. Don't say anything — let the agent speak first.
    vr = VoiceResponse()
    vr.pause(length=2)
    _gather(vr, timeout=15, speech_timeout=2)
    # If agent doesn't speak at all in 15s, silently redirect to retry
    vr.redirect("/handle-silence", method="POST")
    return _twiml(vr)


@app.post("/handle-silence")
async def handle_silence(request: Request):
    """Fallback when <Gather> times out with no speech at all."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")

    conv = conversations.get(call_sid)
    if conv is None:
        vr = VoiceResponse()
        vr.hangup()
        return _twiml(vr)

    conv["silence_count"] = conv.get("silence_count", 0) + 1
    silence = conv["silence_count"]
    logger.info("SILENCE #%d  sid=%s", silence, call_sid)

    if silence >= 3:
        # Three rounds of silence — patient initiates with their opening line
        opening = conv["scenario"].get("opening_line", "Hello, is anyone there?")
        logger.info("Patient initiates: %s", opening[:80])
        conv["logger"].add_entry("PATIENT", opening)
        conv["history"].append({"role": "patient", "text": opening})

        vr = VoiceResponse()
        vr.say(opening, voice=VOICE)
        vr.pause(length=1)
        _gather(vr, timeout=12, speech_timeout=2)
        vr.redirect("/handle-silence", method="POST")
        return _twiml(vr)

    if silence == 2:
        # Second round — say hello
        vr = VoiceResponse()
        vr.say("Hello?", voice=VOICE)
        vr.pause(length=1)
        _gather(vr, timeout=12, speech_timeout=2)
        vr.redirect("/handle-silence", method="POST")
        return _twiml(vr)

    # First round — just wait quietly and listen again
    vr = VoiceResponse()
    vr.pause(length=2)
    _gather(vr, timeout=12, speech_timeout=4)
    vr.redirect("/handle-silence", method="POST")
    return _twiml(vr)


@app.post("/handle-response")
async def handle_response(request: Request):
    """Twilio posts here when <Gather> captures speech."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    agent_text = (form.get("SpeechResult") or "").strip()

    conv = conversations.get(call_sid)
    if conv is None:
        logger.error("No conversation state for sid=%s — hanging up", call_sid)
        vr = VoiceResponse()
        vr.hangup()
        return _twiml(vr)

    # Reset silence counter since we got speech
    conv["silence_count"] = 0
    conv["turns"] += 1
    turn = conv["turns"]

    # Empty speech result — treat like silence
    if not agent_text:
        logger.info("TURN %d  sid=%s  empty speech — redirecting to silence handler", turn, call_sid)
        vr = VoiceResponse()
        vr.redirect("/handle-silence", method="POST")
        return _twiml(vr)

    logger.info("TURN %d  sid=%s  AGENT: %s", turn, call_sid, agent_text)
    conv["logger"].add_entry("AGENT", agent_text)
    conv["history"].append({"role": "agent", "text": agent_text})

    # ── Max-turn safeguard ──────────────────────────────────────────────
    if turn >= MAX_TURNS:
        logger.info("Max turns reached for sid=%s — ending call", call_sid)
        goodbye = "Alright, thank you so much for your help. Have a great day, bye!"
        conv["logger"].add_entry("PATIENT", goodbye)
        conv["history"].append({"role": "patient", "text": goodbye})

        vr = VoiceResponse()
        vr.say(goodbye, voice=VOICE)
        vr.pause(length=1)
        vr.hangup()
        return _twiml(vr)

    # ── Generate patient response via GPT-4o ────────────────────────────
    try:
        patient_text, end_call = await get_patient_response(
            conv["scenario"], conv["history"], agent_text,
        )
        logger.info("PATIENT: %s  (end=%s)", patient_text, end_call)
    except Exception:
        logger.exception("GPT-4o failed")
        patient_text = "I'm sorry, could you repeat that?"
        end_call = False

    conv["logger"].add_entry("PATIENT", patient_text)
    conv["history"].append({"role": "patient", "text": patient_text})

    # ── Respond, then listen for agent's next utterance ─────────────────
    vr = VoiceResponse()
    vr.say(patient_text, voice=VOICE)

    if end_call:
        logger.info("Patient ending call for sid=%s", call_sid)
        vr.pause(length=1)
        vr.hangup()
    else:
        vr.pause(length=1)
        _gather(vr, timeout=12, speech_timeout=1)
        vr.redirect("/handle-silence", method="POST")

    return _twiml(vr)


@app.post("/call-status")
async def call_status(request: Request):
    """Twilio posts here when the call ends."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    duration = form.get("CallDuration", "0")
    status = form.get("CallStatus", "unknown")

    logger.info("CALL ENDED  sid=%s  status=%s  duration=%ss", call_sid, status, duration)

    conv = conversations.pop(call_sid, None)
    if conv:
        filepath = conv["logger"].save(duration=int(duration))
        logger.info("Transcript saved -> %s", filepath)

    return Response(content="OK", media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
