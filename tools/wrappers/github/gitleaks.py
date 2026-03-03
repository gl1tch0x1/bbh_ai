import subprocess
import json
import logging
import os
from pathlib import Path

class GitleaksTool:
    name = "gitleaks"
    categories = ["github", "vuln"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, source: str) -> dict:
        """source can be a local path or a git URL."""
        self.logger.info(f"Running gitleaks on {source}...")
        report_file = self.workspace / "gitleaks_report.json"
        
        try:
            # Usage: gitleaks detect --source=... --report-format=json --report-path=...
            cmd = ["gitleaks", "detect", f"--source={source}", "--report-format=json", f"--report-path={str(report_file)}"]
            
            # Gitleaks exits with code 1 if secrets are found, which is not necessarily a tool failure.
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if report_file.exists():
                with open(report_file, 'r') as f:
                    try:
                        data = json.load(f)
                        if isinstance(data, list):
                            for finding in data:
                                findings.append({
                                    "type": "secret",
                                    "value": finding.get('Secret', ''),
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
                "metadata": {"status": "success" if result.returncode in [0, 1] else "error"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"source": source}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "gitleaks command not found. See https://github.com/gitleaks/gitleaks"}
        except subprocess.TimeoutExpired:
            return {"error": "gitleaks command timed out"}
        except Exception as e:
            return {"error": str(e)}
