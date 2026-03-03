import subprocess
import json
import logging
from pathlib import Path

class DsieveTool:
    name = "dsieve"
    categories = ["subdomains", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, host_list: str) -> dict:
        self.logger.info(f"Running dsieve on {host_list}...")
        try:
            # Usage: dsieve -if host_list
            cmd = ["dsieve", "-if", host_list]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            domains = []
            if result.stdout.strip():
                for line in result.stdout.splitlines():
                    if line.strip():
                        domains.append({"type": "domain_filtered", "value": line.strip(), "source": self.name})

            output = {
                "tool": self.name,
                "inputs": {"host_list": host_list},
                "outputs": {
                    "results": domains,
                    "count": len(domains)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"host_list": host_list}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "dsieve command not found. See https://github.com/trickest/dsieve"}
        except subprocess.TimeoutExpired:
            return {"error": "dsieve command timed out"}
        except Exception as e:
            return {"error": str(e)}
