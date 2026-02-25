# Loom Recording Script (~5 minutes)

Use this as your talking-point guide while screen-sharing. Don't read it word-for-word — just glance at the bullet points and speak naturally.

---

## 1. What I built (30 seconds)

- A Python voice bot that calls Pretty Good AI's test phone number and pretends to be a patient
- It has a full back-and-forth conversation with their AI receptionist
- It records the transcript of every call, then uses GPT-4o to automatically find bugs in how the agent responded

---

## 2. How it works — the call loop (1 minute)

*Show `main.py` on screen while explaining*

- I use **Twilio** to make outbound phone calls to the test number
- When the call connects, Twilio hits my **FastAPI** webhook server running locally (exposed via **ngrok**)
- The server uses Twilio's `<Gather input="speech">` to listen to what the agent says — Twilio transcribes it in real-time and sends the text to my server
- I send that text to **GPT-4o** with a system prompt that says "you are this patient with this scenario" — GPT-4o decides what the patient says next
- The server returns `<Say>` TwiML with the patient's response — Twilio speaks it back to the agent using a neural voice (Amazon Polly)
- Then it immediately starts listening again for the agent's next response
- This loop continues until the conversation naturally ends or we hit 15 turns

---

## 3. The scenarios I tested (1 minute)

*Show `scenarios.py` on screen*

- I wrote 11 different patient scenarios, each designed to test a specific thing
- **Sunday appointment** — sees if the agent books on a closed day
- **HIPAA spouse test** — calls about a spouse's records to see if the agent leaks info without authorization
- **Fake insurance auditor** — pretends to be from Blue Cross doing an audit, asks for patient data
- **Emergency mid-call** — starts with routine scheduling then suddenly reports chest pain — the agent should stop and say call 911
- **Multi-request chaos** — rapid-fires five different requests to see if the agent keeps track
- **Vague escalating symptoms** — starts vague, gradually describes serious symptoms, tests triage ability
- Each scenario has a persona with a name and a specific opening line

---

## 4. What I found — bugs (1 minute)

*Show `bug_report.md` or a couple transcript files*

- Walk through 2-3 specific bugs you found most interesting, for example:
  - Agent said "pretty good AI" to the patient — unprofessional, breaks immersion
  - Agent fabricated a date of birth the patient never gave
  - Agent gave contradictory statements about live transfer availability
  - Agent failed to redirect to 911 when patient reported chest tightness
  - Agent revealed it's a "demo clinic" to a caller
- I ran `bug_analyzer.py` which feeds each transcript to GPT-4o with a QA prompt and generates the full bug report automatically

---

## 5. The biggest problem I faced and how I fixed it (1 minute)

- **Latency was the #1 problem.** My original design used `<Record>` to capture audio, then OpenAI Whisper to transcribe it, then GPT-4o to think, then ElevenLabs to synthesize speech, then `<Play>` to play it back
- That pipeline took **8-12 seconds per turn** — the agent would interpret the silence and start talking again, then my bot's response would come through and cut it off
- **The fix:** I switched from `<Record>` + Whisper + ElevenLabs to `<Gather input="speech">` + `<Say>` — Twilio handles speech recognition and text-to-speech natively, so the only external API call left is GPT-4o
- This brought latency down to **2-3 seconds**, which feels like a natural phone conversation pause

---

## 6. Quick code walkthrough (30 seconds)

*Scroll through the file structure*

- `main.py` — FastAPI server, three endpoints: /voice (call starts), /handle-response (conversation loop), /call-status (call ends, save transcript)
- `call_manager.py` — CLI script that loops through scenarios and tells Twilio to dial the number
- `patient_brain.py` — GPT-4o integration, takes conversation history and returns what the patient says next
- `scenarios.py` — the 11 test scenarios
- `bug_analyzer.py` — reads all transcripts after calls are done, GPT-4o finds bugs, writes bug_report.md
- `transcripts/` — saved text files of every conversation

---

## Wrap up

- 11 calls total, each a different scenario
- Found real bugs: HIPAA issues, fabricated data, broken triage, unprofessional language
- The iteration from the slow Record+Whisper+ElevenLabs design to the fast Gather+Say design was the key learning
