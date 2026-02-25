import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

client = AsyncOpenAI()

BASE_SYSTEM_PROMPT = """\
You are a patient calling a medical or dental office. Stay in character for the entire call.

Rules:
- Speak naturally and conversationally, like a real person on the phone.
- Keep each response to 1-3 sentences — real callers are concise.
- Answer any questions the receptionist asks (name, DOB, insurance, etc.).
- Do NOT rush to end the call. Have a complete, realistic conversation.
- If something in the receptionist's response seems wrong, incorrect, or odd, \
gently push back or ask a clarifying question about it.
- When the conversation has naturally concluded and you have said goodbye, \
append the token [END] at the very end of your message.
- Do NOT include [END] until you have fully wrapped up and said goodbye.\
"""


async def get_patient_response(
    scenario: dict,
    history: list[dict],
    agent_text: str,
) -> tuple[str, bool]:
    """Generate the next patient utterance.

    Returns (response_text, should_end_call).
    """
    system_prompt = (
        BASE_SYSTEM_PROMPT
        + "\n\nYour scenario:\n"
        + scenario["system_prompt"]
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    for entry in history:
        if entry["role"] == "agent":
            messages.append({"role": "user", "content": entry["text"]})
        else:
            messages.append({"role": "assistant", "content": entry["text"]})

    messages.append({"role": "user", "content": agent_text})

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=200,
        temperature=0.8,
    )

    raw = response.choices[0].message.content or ""
    end_call = "[END]" in raw
    text = raw.replace("[END]", "").strip()

    if not text:
        text = "Could you repeat that?"
        end_call = False

    logger.info("Patient brain -> end_call=%s, text=%s", end_call, text[:80])
    return text, end_call
