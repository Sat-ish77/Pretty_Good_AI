"""Analyze call transcripts for bugs and quality issues in the AI agent."""

import os
import asyncio
import logging

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("bug_analyzer")

client = AsyncOpenAI()

TRANSCRIPT_DIR = "transcripts"

ANALYSIS_PROMPT = """\
You are a senior QA engineer reviewing a medical / dental receptionist AI agent.
Read the call transcript below carefully. Your job is to find **2 to 4 concrete
bugs or quality issues and prioritize them by severity.** in the AGENT's responses.

Focus on things like:
- Incorrect information (wrong hours, wrong procedures, bad medical advice)
- Privacy / HIPAA violations (sharing info without authorization)
- Unprofessional language or broken sentences
- Failing to answer the patient's actual question
- Confirming impossible things (appointments on closed days, nonexistent doctors)
- Losing context or contradicting itself
- Missing safety warnings for urgent symptoms
- Revealing internal/demo/system details to the caller

For **each** issue, use this exact format:

**Bug**: One-line description
**Severity**: High / Medium / Low
**Location**: Quote the relevant AGENT line(s) from the transcript
**Details**: What happened, why it is a problem, and what the agent should
have done instead.

You MUST find at least 2 issues. If the transcript is very short or empty,
note that as a bug itself (agent failed to engage / call dropped).

---

{transcript}
"""


async def analyze_transcript(filepath: str, max_retries: int = 3) -> str:
    """Send one transcript to GPT-4o for analysis, with retries."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if len(content.strip()) < 50:
        return (
            "**Bug**: Transcript is empty or nearly empty — call failed to produce a conversation\n"
            "**Severity**: High\n"
            "**Location**: Entire transcript\n"
            "**Details**: The agent either did not answer, disconnected immediately, "
            "or the call failed before any meaningful exchange occurred."
        )

    for attempt in range(max_retries):
        try:
            resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a thorough QA engineer. Always provide detailed analysis."},
                    {"role": "user", "content": ANALYSIS_PROMPT.format(transcript=content)},
                ],
                max_tokens=2000,
                temperature=0.4,
            )

            result = (resp.choices[0].message.content or "").strip()

            if len(result) > 50:
                return result

            logger.warning(
                "Empty/short response for %s (attempt %d/%d)",
                os.path.basename(filepath), attempt + 1, max_retries,
            )
        except Exception as exc:
            logger.warning(
                "API error for %s (attempt %d/%d): %s",
                os.path.basename(filepath), attempt + 1, max_retries, exc,
            )

        await asyncio.sleep(2 * (attempt + 1))

    return "_Analysis failed after multiple retries. Review this transcript manually._"


async def analyze_all():
    """Iterate over every transcript and produce bug_report.md."""
    if not os.path.exists(TRANSCRIPT_DIR):
        print("No transcripts/ directory found. Run calls first.")
        return

    files = sorted(f for f in os.listdir(TRANSCRIPT_DIR) if f.endswith(".txt"))
    if not files:
        print("No transcript files found in transcripts/.")
        return

    print(f"Analyzing {len(files)} transcript(s)...\n")

    sections: list[str] = [
        "# Bug Report\n",
        f"Auto-generated from **{len(files)}** call transcripts.\n",
    ]

    success = 0
    for i, filename in enumerate(files):
        filepath = os.path.join(TRANSCRIPT_DIR, filename)
        print(f"  [{i + 1}/{len(files)}] {filename} ... ", end="", flush=True)

        analysis = await analyze_transcript(filepath)

        if analysis and not analysis.startswith("_Analysis failed"):
            success += 1
            print("OK")
        else:
            print("RETRY EXHAUSTED")

        sections.append(f"\n---\n\n## {filename}\n\n{analysis}\n")

    report = "\n".join(sections)

    with open("bug_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nDone: {success}/{len(files)} transcripts analyzed successfully.")
    print("Bug report saved to bug_report.md")


if __name__ == "__main__":
    asyncio.run(analyze_all())
