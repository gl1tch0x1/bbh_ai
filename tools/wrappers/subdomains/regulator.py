import subprocess
import json
import logging
import os
from pathlib import Path

class RegulatorTool:
    name = "regulator"
    categories = ["subdomains", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, domain: str, subdomains_file: str) -> dict:
        self.logger.info(f"Running regulator on {domain}...")
        output_file = self.workspace / f"regulator_{domain}.txt"
        
        try:
            # Usage: python3 regulator.py <domain> <subdomains_file> <output_file>
            cmd = ["python3", "regulator.py", domain, subdomains_file, str(output_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            domains = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    domains = [{"type": "domain_predicted", "value": line.strip(), "source": self.name} 
                               for line in f if line.strip()]

            output = {
                "tool": self.name,
                "inputs": {"domain": domain, "subdomains_file": subdomains_file},
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
            return {"error": "regulator.py not found. See https://github.com/cramppet/regulator"}
        except subprocess.TimeoutExpired:
            return {"error": "regulator command timed out"}
        except Exception as e:
            return {"error": str(e)}
