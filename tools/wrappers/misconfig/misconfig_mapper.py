import subprocess
import json
import logging
import os
from pathlib import Path

class MisconfigMapperTool:
    name = "misconfig_mapper"
    categories = ["misconfig", "vuln", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, target: str) -> dict:
        self.logger.info(f"Running misconfig-mapper on {target}...")
        output_file = self.workspace / f"misconfig_{target}.json"
        
        try:
            # Usage: misconfig-mapper -t target -o json > output.json
            cmd = ["misconfig-mapper", "-t", target, "-o", "json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    # Normalize misconfig-mapper structure
                    for finding in data:
                        findings.append({
                            "type": "misconfig",
                            "value": target,
                            "source": self.name,
                            "metadata": finding
                        })
                except json.JSONDecodeError:
                    pass
            
            output = {
                "tool": self.name,
                "inputs": {"target": target},
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
            return {"error": "misconfig-mapper command not found. See https://github.com/intigriti/misconfig-mapper"}
        except subprocess.TimeoutExpired:
            return {"error": "misconfig-mapper command timed out"}
        except Exception as e:
            return {"error": str(e)}
