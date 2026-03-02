import json
import time
from pathlib import Path

class Telemetry:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.data = {
            "start_time": time.time(),
            "agent_logs": [],
            "tool_calls": [],
            "errors": []
        }

    def log_agent_action(self, agent, action, details):
        self.data["agent_logs"].append({
            "timestamp": time.time(),
            "agent": agent,
            "action": action,
            "details": details
        })

    def log_tool_call(self, tool, args, result_summary):
        self.data["tool_calls"].append({
            "timestamp": time.time(),
            "tool": tool,
            "args": args,
            "result_summary": result_summary
        })

    def log_error(self, error):
        self.data["errors"].append({
            "timestamp": time.time(),
            "error": str(error)
        })

    def save(self):
        self.data["end_time"] = time.time()
        with open(self.filepath, 'w') as f:
            json.dump(self.data, f, indent=2)