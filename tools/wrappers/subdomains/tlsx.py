import subprocess
import json
import logging
from pathlib import Path

class TlsxTool:
    name = "tlsx"
    categories = ["subdomains", "hosts", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, host_list: str = None, domain: str = None) -> dict:
        self.logger.info(f"Running tlsx...")
        try:
            cmd = ["tlsx", "-json", "-silent", "-san", "-cn"]
            if host_list:
                cmd.extend(["-l", host_list])
            elif domain:
                cmd.extend(["-d", domain])
            else:
                return {"error": "host_list or domain must be provided to tlsx"}

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                for line in result.stdout.splitlines():
                    if line.strip():
                        try:
                            findings.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            output = {
                "tool": self.name,
                "inputs": {"host_list": host_list, "domain": domain},
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
            return {"error": "tlsx command not found. See https://github.com/projectdiscovery/tlsx"}
        except subprocess.TimeoutExpired:
            return {"error": "tlsx command timed out"}
        except Exception as e:
            return {"error": str(e)}
