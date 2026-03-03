import subprocess
import json
import logging
from pathlib import Path

class GotatorTool:
    name = "gotator"
    categories = ["subdomains", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, subdomains_file: str, permutations_file: str = None) -> dict:
        self.logger.info(f"Running gotator on {subdomains_file}...")
        try:
            # Usage: gotator -sub subdomains.txt -perm permutations.txt -silent
            cmd = ["gotator", "-sub", subdomains_file, "-silent"]
            if permutations_file:
                cmd.extend(["-perm", permutations_file])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            domains = []
            if result.stdout.strip():
                for line in result.stdout.splitlines():
                    if line.strip():
                        domains.append({"type": "domain_permutation", "value": line.strip(), "source": self.name})

            output = {
                "tool": self.name,
                "inputs": {"subdomains_file": subdomains_file, "permutations_file": permutations_file},
                "outputs": {
                    "results": domains,
                    "count": len(domains)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"subdomains_file": subdomains_file}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "gotator command not found. See https://github.com/JosueEncinar/gotator"}
        except subprocess.TimeoutExpired:
            return {"error": "gotator command timed out"}
        except Exception as e:
            return {"error": str(e)}
