import json
import time
import threading
from pathlib import Path


class Telemetry:
    """Thread-safe telemetry collector that persists data to disk on save()."""

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self._lock = threading.Lock()
        self.data = {
            "start_time": time.time(),
            "start_time_iso": time.strftime('%Y-%m-%dT%H:%M:%S'),
            "agent_logs": [],
            "tool_calls": [],
            "errors": [],
        }

    def log_agent_action(self, agent: str, action: str, details):
        entry = {
            "timestamp": time.time(),
            "agent": agent,
            "action": action,
            "details": details,
        }
        with self._lock:
            self.data["agent_logs"].append(entry)

    def log_tool_call(self, tool: str, args: dict, result_summary):
        entry = {
            "timestamp": time.time(),
            "tool": tool,
            "args": args,
            "result_summary": result_summary,
        }
        with self._lock:
            self.data["tool_calls"].append(entry)

    def log_error(self, error):
        entry = {
            "timestamp": time.time(),
            "error": str(error),
        }
        with self._lock:
            self.data["errors"].append(entry)

    def save(self):
        """Persist telemetry data to disk. Called by Orchestrator in a finally block."""
        with self._lock:
            self.data["end_time"] = time.time()
            self.data["end_time_iso"] = time.strftime('%Y-%m-%dT%H:%M:%S')
            duration = self.data["end_time"] - self.data["start_time"]
            self.data["duration_seconds"] = round(duration, 2)
            payload = dict(self.data)

        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, default=str)