import subprocess
import json
import logging
from pathlib import Path

class PurednsTool:
    name = "puredns"
    categories = ["subdomains", "dns", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, host_list: str, resolvers: str = None) -> dict:
        self.logger.info(f"Running puredns on {host_list}...")
        output_file = self.workspace / "puredns_resolved.txt"
        
        try:
            # Usage: puredns resolve host_list --resolvers resolvers.txt --write output.txt
            cmd = ["puredns", "resolve", host_list, "--write", str(output_file)]
            
            resolvers_path = resolvers or (self.config or {}).get('tools', {}).get('puredns', {}).get('resolvers')
            if resolvers_path:
                cmd.extend(["--resolvers", resolvers_path])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            domains = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    domains = [line.strip() for line in f if line.strip()]

            output = {
                "tool": self.name,
                "inputs": {"host_list": host_list, "resolvers": resolvers_path},
                "outputs": {
                    "results": [
                        {"type": "domain", "value": d, "source": self.name}
                        for d in domains
                    ],
                    "count": len(domains)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"host_list": host_list}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "puredns command not found. See https://github.com/d3mondev/puredns"}
        except subprocess.TimeoutExpired:
            return {"error": "puredns command timed out"}
        except Exception as e:
            return {"error": str(e)}
