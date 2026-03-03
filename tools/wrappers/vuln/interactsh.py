import subprocess
import json
import logging
import os
import re
from pathlib import Path

class InteractshTool:
    name = "interactsh"
    categories = ["vuln", "extras", "oob"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        # Default behavior: generate a new session or use existing one
        self.session_file = workspace / "interactsh_session.json" if workspace else Path("interactsh_session.json")
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, mode: str = "generate", payload_count: int = 1) -> dict:
        """
        Modes:
        - generate: Creates a new session/URL.
        - poll: Checks for interactions.
        """
        if mode == "generate":
            return self._generate(payload_count)
        elif mode == "poll":
            return self._poll()
        else:
            return {"error": f"Unsupported mode: {mode}"}

    def _generate(self, count: int) -> dict:
        self.logger.info(f"Generating {count} interactsh payloads...")
        try:
            # Command to generate payload and store session
            # interactsh-client -n 1 -sf session.json
            cmd = ["interactsh-client", "-n", str(count), "-sf", str(self.session_file), "-ps", "-silent"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Extract URL from stdout
            # Output usually looks like: [INF] c2v...interact.sh
            urls = []
            for line in result.stdout.splitlines():
                if "interact.sh" in line or "oast." in line:
                    match = re.search(r'([a-z0-9]+\.(interact\.sh|oast\.[a-z]+|pro))', line)
                    if match:
                        urls.append(match.group(1))

            output = {
                "tool": self.name,
                "inputs": {"mode": "generate", "count": count},
                "outputs": {
                    "urls": urls,
                    "session_file": str(self.session_file)
                },
                "metadata": {"status": "success" if urls else "warning"}
            }
            return output

        except Exception as e:
            return {"error": str(e)}

    def _poll(self) -> dict:
        self.logger.info(f"Polling interactsh interactions for session {self.session_file}...")
        if not self.session_file.exists():
            return {"error": "Session file not found. Run in 'generate' mode first."}

        try:
            # Poll interactions in JSON mode and exit
            # We use a small timeout to poll and then quit
            cmd = ["interactsh-client", "-sf", str(self.session_file), "-json", "-ps", "-silent"]
            # Note: interactsh-client keeps polling. We might need to kill it or use a specific flag if available.
            # In latest versions, it polls and prints. To make it "one-off", we might need a timeout.
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10) # 10s polling
            except subprocess.TimeoutExpired as e:
                # Capture what it found before timing out
                stdout = e.stdout if e.stdout else ""
            else:
                stdout = result.stdout

            interactions = []
            if stdout:
                for line in stdout.splitlines():
                    if line.strip().startswith("{"):
                        try:
                            interactions.append(json.loads(line))
                        except:
                            continue

            output = {
                "tool": self.name,
                "inputs": {"mode": "poll"},
                "outputs": {
                    "results": [
                        {"type": "oob_interaction", "value": i.get('full-id'), "source": self.name, "metadata": i}
                        for i in interactions
                    ],
                    "count": len(interactions)
                },
                "metadata": {"status": "success"}
            }
            return output

        except Exception as e:
            return {"error": str(e)}
