import subprocess
import json
import logging
import re
from pathlib import Path

class PorchPirateTool:
    name = "porch_pirate"
    categories = ["osint", "api_leaks"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, keyword: str) -> dict:
        self.logger.info(f"Running porch-pirate on keyword: {keyword}...")
        try:
            # Usage: porch-pirate -s "keyword" --json
            cmd = ["porch-pirate", "-s", keyword, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                try:
                    # Attempt to parse JSON output if tool supports it; 
                    # otherwise parse text lines.
                    data = json.loads(result.stdout)
                    findings = self._normalize_json(data)
                except json.JSONDecodeError:
                    findings = self._parse_text(result.stdout)
            
            output = {
                "tool": self.name,
                "inputs": {"keyword": keyword},
                "outputs": {
                    "results": [
                        {"type": "api_leak", "value": f.get('id', keyword), "source": self.name, "metadata": f}
                        for f in findings
                    ]
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"keyword": keyword}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "porch-pirate command not found. See https://github.com/dtail-io/porch-pirate"}
        except subprocess.TimeoutExpired:
            return {"error": "porch-pirate command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _normalize_json(self, data) -> list:
        # Placeholder for normalizing tool-specific JSON to our list format
        if isinstance(data, list): return data
        if isinstance(data, dict): return data.get('workspaces', []) or data.get('collections', [])
        return []

    def _parse_text(self, text: str) -> list:
        # Placeholder for basic line-by-line parsing if JSON flag isn't respected
        return [{"raw_line": line} for line in text.splitlines() if line.strip()]
