import subprocess
import json
import re
import logging
from pathlib import Path

class WhoisTool:
    name = "whois"
    categories = ["osint", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 30)

    def run(self, target: str) -> dict:
        self.logger.info(f"Running whois on {target}...")
        try:
            cmd = ["whois", target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "whois command failed"}

            parsed = self._parse_whois(result.stdout)
            
            output = {
                "tool": self.name,
                "inputs": {"target": target},
                "outputs": {
                    "results": [
                        {
                            "type": "whois_record",
                            "value": target,
                            "source": self.name,
                            "metadata": parsed
                        }
                    ],
                    "raw": result.stdout
                },
                "metadata": {"status": "success"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"target": target}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "whois command not found. Please install it (e.g., sudo apt install whois)."}
        except subprocess.TimeoutExpired:
            return {"error": "whois command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_whois(self, text: str) -> dict:
        """Simple regex parser for whois output."""
        patterns = {
            "registrar": r"Registrar:\s*(.*)",
            "expiry_date": r"Registry Expiry Date:\s*(.*)",
            "creation_date": r"Creation Date:\s*(.*)",
            "registrant_org": r"Registrant Organization:\s*(.*)",
            "name_servers": r"Name Server:\s*(.*)"
        }
        
        parsed = {}
        for key, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Name servers can be multiple
                if key == "name_servers":
                    parsed[key] = [m.strip() for m in matches]
                else:
                    parsed[key] = matches[0].strip()
        
        return parsed
