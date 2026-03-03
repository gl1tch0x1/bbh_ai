import subprocess
import json
import logging
import os
from pathlib import Path

class XnldorkerTool:
    name = "xnldorker"
    categories = ["osint", "dorking"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running xnldorker on {domain}...")
        output_file = self.workspace / f"xnldorker_{domain}.txt"
        
        try:
            # Usage: xnldorker -d domain.com -o output.txt
            cmd = ["xnldorker", "-d", domain, "-o", str(output_file)]
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
            return {"error": "xnldorker command not found. Install via: pip install xnldorker"}
        except subprocess.TimeoutExpired:
            return {"error": "xnldorker command timed out"}
        except Exception as e:
            return {"error": str(e)}
