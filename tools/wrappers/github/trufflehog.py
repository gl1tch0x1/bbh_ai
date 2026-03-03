import subprocess
import json
import logging
from pathlib import Path

class TrufflehogTool:
    name = "trufflehog"
    categories = ["github", "vuln", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, target: str, type: str = "github") -> dict:
        """target can be an org name, repo URL, or github user."""
        self.logger.info(f"Running trufflehog on {target} ({type})...")
        try:
            # Usage for github org: trufflehog github --org=target --json
            # Usage for single repo: trufflehog github --repo=target --json
            cmd = ["trufflehog", type]
            if "github.com" in target:
                cmd.append(f"--repo={target}")
            else:
                cmd.append(f"--org={target}")
            cmd.append("--json")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                # Trufflehog outputs individual JSON objects per line
                for line in result.stdout.splitlines():
                    if line.strip():
                        try:
                            finding = json.loads(line)
                            findings.append({
                                "type": "secret",
                                "value": finding.get('Raw', ''),
                                "source": self.name,
                                "metadata": finding
                            })
                        except json.JSONDecodeError:
                            continue

            output = {
                "tool": self.name,
                "inputs": {"target": target, "type": type},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"target": target}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "trufflehog command not found. See https://github.com/trufflesecurity/trufflehog"}
        except subprocess.TimeoutExpired:
            return {"error": "trufflehog command timed out"}
        except Exception as e:
            return {"error": str(e)}
