import subprocess
import json
import logging
from pathlib import Path

class VhostfinderTool:
    name = "vhostfinder"
    categories = ["hosts", "web", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running vhostfinder on {domain}...")
        try:
            # Usage: vhostfinder -d domain.com
            cmd = ["vhostfinder", "-d", domain]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            vhosts = []
            if result.stdout.strip():
                for line in result.stdout.splitlines():
                    if line.strip() and "." in line:
                        vhosts.append({"type": "vhost", "value": line.strip(), "source": self.name})

            output = {
                "tool": self.name,
                "inputs": {"domain": domain},
                "outputs": {
                    "results": vhosts,
                    "count": len(vhosts)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"domain": domain}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "vhostfinder command not found. See https://github.com/m4ll0k/vhostfinder"}
        except subprocess.TimeoutExpired:
            return {"error": "vhostfinder command timed out"}
        except Exception as e:
            return {"error": str(e)}
