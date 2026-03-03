import subprocess
import json
import logging
from pathlib import Path

class TitusTool:
    name = "titus"
    categories = ["github", "vuln"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, source: str) -> dict:
        """source can be a local path or a git URL."""
        self.logger.info(f"Running titus on {source}...")
        try:
            # Usage: titus scan <source> --sarif output.sarif
            # We will use stdout and parse the structured output if possible
            cmd = ["titus", "scan", source, "--format", "json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    # Titus JSON structure normalization
                    for finding in data.get('findings', []):
                        findings.append({
                            "type": "secret",
                            "value": finding.get('secret', ''),
                            "source": self.name,
                            "metadata": finding
                        })
                except json.JSONDecodeError:
                    pass
            
            output = {
                "tool": self.name,
                "inputs": {"source": source},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "error"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"source": source}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "titus command not found. See https://github.com/praetorian-inc/titus"}
        except subprocess.TimeoutExpired:
            return {"error": "titus command timed out"}
        except Exception as e:
            return {"error": str(e)}
