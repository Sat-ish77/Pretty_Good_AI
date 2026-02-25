import os
from datetime import datetime

TRANSCRIPT_DIR = "transcripts"


class TranscriptLogger:
    def __init__(self, scenario_name: str, call_sid: str):
        self.scenario_name = scenario_name
        self.call_sid = call_sid
        self.start_time = datetime.now()
        self.entries: list[dict] = []

    def add_entry(self, role: str, text: str):
        self.entries.append({"role": role.upper(), "text": text})

    def save(self, duration: int = 0) -> str:
        os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
        filename = f"{self.scenario_name}_{self.call_sid[:8]}.txt"
        filepath = os.path.join(TRANSCRIPT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(f"SCENARIO: {self.scenario_name}\n")
            f.write(f"CALL SID: {self.call_sid}\n")
            f.write(f"DATE: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("---\n\n")

            for entry in self.entries:
                f.write(f"[{entry['role']}]: {entry['text']}\n\n")

            f.write(f"--- CALL ENDED (duration: {duration}s) ---\n")

        return filepath
