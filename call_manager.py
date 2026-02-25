"""Initiate outbound calls to the Pretty Good AI test line."""

import os
import sys
import time
import argparse
import logging

from twilio.rest import Client
from dotenv import load_dotenv

from scenarios import SCENARIOS

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("call_manager")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER", "")
TARGET_PHONE = os.getenv("TARGET_PHONE_NUMBER", "+18054398008")
NGROK_URL = os.getenv("NGROK_URL", "").rstrip("/")

DELAY_BETWEEN_CALLS = 120  # seconds


def make_call(scenario_name: str) -> str:
    """Place one outbound call for the given scenario. Returns the CallSid."""
    client = Client(TWILIO_SID, TWILIO_TOKEN)

    call = client.calls.create(
        to=TARGET_PHONE,
        from_=TWILIO_PHONE,
        url=f"{NGROK_URL}/voice?scenario={scenario_name}",
        status_callback=f"{NGROK_URL}/call-status",
        status_callback_event=["completed"],
        record=True,
        recording_channels="mono",
        timeout=60,
    )

    logger.info("Call created  sid=%s  scenario=%s", call.sid, scenario_name)
    return call.sid


def run_scenarios(names: list[str] | None = None, delay: int = DELAY_BETWEEN_CALLS):
    """Run one or more scenarios sequentially with a pause between each."""
    if not NGROK_URL:
        sys.exit("ERROR: NGROK_URL is not set in .env — start ngrok first.")
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_PHONE:
        sys.exit("ERROR: Twilio credentials are missing from .env")

    if names:
        selected = [s for s in SCENARIOS if s["name"] in names]
        if not selected:
            sys.exit(f"ERROR: No scenarios matched {names}. Available: {[s['name'] for s in SCENARIOS]}")
    else:
        selected = SCENARIOS

    print(f"\n{'=' * 55}")
    print(f"  Voice Bot — Running {len(selected)} scenario(s)")
    print(f"  Target : {TARGET_PHONE}")
    print(f"  From   : {TWILIO_PHONE}")
    print(f"  Webhook: {NGROK_URL}")
    print(f"{'=' * 55}\n")

    for i, scenario in enumerate(selected):
        print(f"[{i + 1}/{len(selected)}] {scenario['name']}")
        try:
            sid = make_call(scenario["name"])
            print(f"  → Call SID: {sid}")
        except Exception as exc:
            print(f"  ✗ Failed: {exc}")
            continue

        if i < len(selected) - 1:
            print(f"  Waiting {delay}s before next call…")
            time.sleep(delay)

    print(f"\n{'=' * 55}")
    print("  Done! Check transcripts/ for results.")
    print("  Run  python bug_analyzer.py  to generate the bug report.")
    print(f"{'=' * 55}\n")


def main():
    parser = argparse.ArgumentParser(description="Place outbound test calls")
    parser.add_argument(
        "--scenario", "-s",
        nargs="*",
        help="Run specific scenario(s) by name. Omit to run all.",
    )
    parser.add_argument(
        "--delay", "-d",
        type=int,
        default=DELAY_BETWEEN_CALLS,
        help=f"Seconds to wait between calls (default {DELAY_BETWEEN_CALLS})",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available scenarios and exit",
    )

    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for s in SCENARIOS:
            print(f"  • {s['name']}")
        return

    run_scenarios(names=args.scenario, delay=args.delay)


if __name__ == "__main__":
    main()
