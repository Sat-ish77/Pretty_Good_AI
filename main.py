from dotenv import load_dotenv
load_dotenv()

import os
import logging
import random
import asyncio
import time
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse
from openai import AsyncOpenAI

from scenarios import SCENARIOS
from patient_brain import get_patient_response
from voice_synthesizer import synthesize_speech
from transcript_logger import TranscriptLogger

FILLER_TEXTS = [
    # Short — always safe
    "Mmmm..",
    "Mmhmm..",
    "Okayyy...",
    # Long — only used when certain
    "Ummm let me think about that...",
    "Mmhmm yeah...",
    "Okayyy so...",
    "Ummm let me think...",
]
filler_audio_files: list[str] = []
_last_filler_index: int = -1
response_cache: dict[str, tuple | None] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("voicebot")

_warmup_client = AsyncOpenAI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global filler_audio_files
    logger.info("Pre-generating filler audio files...")
    for text in FILLER_TEXTS:
        try:
            audio_file = await synthesize_speech(text)
            filler_audio_files.append(audio_file)
            logger.info("Filler ready: %s -> %s", text, audio_file)
        except Exception:
            logger.warning("Failed to pre-generate filler: %s", text)
    logger.info("Pre-generation complete. %d fillers ready.", len(filler_audio_files))

    try:
        logger.info("Warming up OpenAI...")
        await _warmup_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        logger.info("OpenAI warm-up complete.")
    except Exception:
        logger.warning("OpenAI warm-up failed — Turn 1 may be slow")

    yield


app = FastAPI(title="Voice Bot — Pretty Good AI Tester", lifespan=lifespan)

NGROK_URL = os.getenv("NGROK_URL", "").rstrip("/")
MAX_TURNS = 15
VOICE = os.getenv("TTS_VOICE", "Polly.Matthew-Neural")

conversations: dict[str, dict] = {}

os.makedirs("transcripts", exist_ok=True)
os.makedirs("audio_cache", exist_ok=True)

app.mount("/audio", StaticFiles(directory="audio_cache"), name="audio")


def _pick_filler() -> str | None:
    """Pick a filler audio file, never repeating the last one."""
    global _last_filler_index
    if not filler_audio_files:
        return None
    available = [i for i in range(len(filler_audio_files)) if i != _last_filler_index]
    idx = random.choice(available)
    _last_filler_index = idx
    return filler_audio_files[idx]


def _pick_smart_filler(agent_text: str, history: list[dict]) -> str | None:
    """Pick a contextually appropriate filler based on what the agent just said."""
    if not filler_audio_files:
        return None

    text = agent_text.lower()
    turns = len(history)

    # ── HIGH CERTAINTY → quick acknowledgment for personal info ──
    if "spell" in text:
        filler_text = "Okayyy..."
    elif any(w in text for w in ["date of birth", "dob", "birthday"]):
        filler_text = "Mmhmm.."
    elif any(w in text for w in ["is that correct", "is that right", "confirm"]):
        filler_text = "Mmhmm yeah..."
    elif any(w in text for w in ["would you prefer"]):
        filler_text = "Okayyy so..."
    elif any(w in text for w in ["full name", "your name"]):
        filler_text = "Okayyy..."
    elif any(w in text for w in ["phone number", "number on file"]):
        filler_text = "Mmhmm.."

    # ── LOW CERTAINTY → short safe sounds only ──
    elif turns <= 3:
        filler_text = random.choice(["Mmmm..", "Okayyy..."])
    elif "?" in agent_text:
        filler_text = random.choice(["Mmmm..", "Mmhmm.."])
    elif any(w in text for w in ["unfortunately", "unable", "cannot", "can't"]):
        filler_text = "Mmmm.."
    elif any(w in text for w in ["great", "perfect", "got it"]):
        filler_text = "Mmhmm.."
    else:
        filler_text = random.choice(["Mmmm..", "Mmhmm.."])

    # Match text to pre-generated file
    if filler_text in FILLER_TEXTS:
        idx = FILLER_TEXTS.index(filler_text)
        if idx < len(filler_audio_files):
            return filler_audio_files[idx]

    return _pick_filler()


def _twiml(vr: VoiceResponse) -> Response:
    return Response(content=str(vr), media_type="application/xml")


def _gather(vr: VoiceResponse, timeout: int = 12, speech_timeout: int = 1):
    vr.gather(
        input="speech",
        action="/handle-response",
        speech_timeout=str(speech_timeout),
        timeout=timeout,
        language="en-US",
    )


async def _speak(vr: VoiceResponse, text: str, play_filler: bool = False):
    """Speak text using ElevenLabs, falling back to Polly if it fails."""
    if play_filler:
        filler = _pick_filler()
        if filler:
            vr.play(f"{NGROK_URL}/audio/{filler}")

    try:
        audio_file = await synthesize_speech(text)
        vr.play(f"{NGROK_URL}/audio/{audio_file}")
    except Exception:
        logger.warning("ElevenLabs failed — falling back to Polly")
        vr.say(text, voice=VOICE)


async def _process_and_cache(call_sid: str, conv: dict, agent_text: str):
    """Run GPT + ElevenLabs in background and store result in response_cache."""
    t1 = time.time()
    try:
        patient_text, end_call = await get_patient_response(
            conv["scenario"], conv["history"], agent_text,
        )
        t2 = time.time()
        logger.info("PATIENT: %s  (end=%s)", patient_text, end_call)
    except Exception:
        logger.exception("GPT-4o-mini failed")
        patient_text = "I'm sorry, could you repeat that?"
        end_call = False
        t2 = time.time()

    try:
        audio_file = await synthesize_speech(patient_text)
        t3 = time.time()
    except Exception:
        logger.exception("ElevenLabs failed in background task")
        audio_file = "__fallback__"
        t3 = time.time()

    logger.info("LATENCY  GPT=%.2fs  ElevenLabs=%.2fs  total=%.2fs", t2 - t1, t3 - t2, t3 - t1)

    conv["logger"].add_entry("PATIENT", patient_text)
    conv["history"].append({"role": "patient", "text": patient_text})
    response_cache[call_sid] = (audio_file, patient_text, end_call)


# ── Webhooks ────────────────────────────────────────────────────────────

@app.post("/voice")
async def voice_webhook(request: Request):
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

    vr = VoiceResponse()
    vr.pause(length=4)
    _gather(vr, timeout=15, speech_timeout=2)
    vr.redirect("/handle-silence", method="POST")
    return _twiml(vr)


@app.post("/handle-silence")
async def handle_silence(request: Request):
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
        opening = conv["scenario"].get("opening_line", "Hello, is anyone there?")
        logger.info("Patient initiates: %s", opening[:80])
        conv["logger"].add_entry("PATIENT", opening)
        conv["history"].append({"role": "patient", "text": opening})

        vr = VoiceResponse()
        await _speak(vr, opening)
        vr.pause(length=1)
        _gather(vr, timeout=12, speech_timeout=2)
        vr.redirect("/handle-silence", method="POST")
        return _twiml(vr)

    if silence == 2:
        vr = VoiceResponse()
        vr.say("Hello?", voice=VOICE)
        vr.pause(length=1)
        _gather(vr, timeout=12, speech_timeout=2)
        vr.redirect("/handle-silence", method="POST")
        return _twiml(vr)

    vr = VoiceResponse()
    vr.pause(length=2)
    _gather(vr, timeout=12, speech_timeout=4)
    vr.redirect("/handle-silence", method="POST")
    return _twiml(vr)


@app.post("/handle-response")
async def handle_response(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    agent_text = (form.get("SpeechResult") or "").strip()

    conv = conversations.get(call_sid)
    if conv is None:
        logger.error("No conversation state for sid=%s — hanging up", call_sid)
        vr = VoiceResponse()
        vr.hangup()
        return _twiml(vr)

    conv["silence_count"] = 0
    conv["turns"] += 1
    turn = conv["turns"]

    if not agent_text:
        logger.info("TURN %d  sid=%s  empty speech — redirecting to silence handler", turn, call_sid)
        vr = VoiceResponse()
        vr.redirect("/handle-silence", method="POST")
        return _twiml(vr)

    logger.info("TURN %d  sid=%s  AGENT: %s", turn, call_sid, agent_text)
    conv["logger"].add_entry("AGENT", agent_text)
    conv["history"].append({"role": "agent", "text": agent_text})

    if turn >= MAX_TURNS:
        logger.info("Max turns reached for sid=%s — ending call", call_sid)
        goodbye = "Alright, thank you so much for your help. Have a great day, bye!"
        conv["logger"].add_entry("PATIENT", goodbye)
        conv["history"].append({"role": "patient", "text": goodbye})

        vr = VoiceResponse()
        await _speak(vr, goodbye)
        vr.pause(length=1)
        vr.hangup()
        return _twiml(vr)

    # ── Phase 1: kick off background processing, immediately return filler ──
    response_cache[call_sid] = None
    asyncio.create_task(_process_and_cache(call_sid, conv, agent_text))

    vr = VoiceResponse()
    filler = _pick_smart_filler(agent_text, conv["history"])
    if filler:
        vr.play(f"{NGROK_URL}/audio/{filler}")
    vr.pause(length=1)
    vr.redirect("/get-response", method="POST")
    return _twiml(vr)


@app.post("/get-response")
async def get_response(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")

    result = response_cache.get(call_sid)

    if result is None:
        logger.info("get-response: still processing for sid=%s — waiting", call_sid)
        vr = VoiceResponse()
        vr.pause(length=1)
        vr.redirect("/get-response", method="POST")
        return _twiml(vr)

    del response_cache[call_sid]
    audio_file, patient_text, end_call = result
    logger.info("get-response: delivering response for sid=%s", call_sid)

    vr = VoiceResponse()
    if audio_file == "__fallback__":
        vr.say("I'm sorry, could you repeat that?", voice=VOICE)
    else:
        vr.play(f"{NGROK_URL}/audio/{audio_file}")

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