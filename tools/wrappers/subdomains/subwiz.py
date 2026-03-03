import subprocess
import json
import logging
from pathlib import Path

class SubwizTool:
    name = "subwiz"
    categories = ["subdomains", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running subwiz on {domain}...")
        try:
            # Usage: subwiz -d domain.com
            cmd = ["subwiz", "-d", domain]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            domains = []
            if result.stdout.strip():
                for line in result.stdout.splitlines():
                    if line.strip():
                        domains.append({"type": "domain", "value": line.strip(), "source": self.name})

            output = {
                "tool": self.name,
                "inputs": {"domain": domain},
                "outputs": {
                    "results": domains,
                    "count": len(domains)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"domain": domain}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "subwiz command not found. See https://github.com/dmdark/subwiz"}
        except subprocess.TimeoutExpired:
            return {"error": "subwiz command timed out"}
        except Exception as e:
            return {"error": str(e)}
