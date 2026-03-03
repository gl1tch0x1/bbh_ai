import subprocess
import json
import logging
import os
from pathlib import Path

class DorksHunterTool:
    name = "dorks_hunter"
    categories = ["osint", "dorking"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running dorks_hunter on {domain}...")
        output_file = self.workspace / f"dorks_hunter_{domain}.txt"
        
        try:
            # Usage: python3 dorks_hunter.py -d domain.com -o output.txt
            cmd = ["python3", "dorks_hunter.py", "-d", domain, "-o", str(output_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            findings.append({"type": "dork_result", "value": line.strip(), "source": self.name})

            output = {
                "tool": self.name,
                "inputs": {"domain": domain},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"domain": domain}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "dorks_hunter script not found. See https://github.com/six2dez/dorks_hunter"}
        except subprocess.TimeoutExpired:
            return {"error": "dorks_hunter command timed out"}
        except Exception as e:
            return {"error": str(e)}
