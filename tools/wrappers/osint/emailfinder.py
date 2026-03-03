import subprocess
import json
import logging
import re
from pathlib import Path

class EmailfinderTool:
    name = "emailfinder"
    categories = ["osint", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 120)  # OSINT can be slow

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running emailfinder on {domain}...")
        try:
            # Usage: emailfinder -d domain.com
            cmd = ["emailfinder", "-d", domain]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            # The tool might output emails directly to stdout
            emails = self._extract_emails(result.stdout)
            
            output = {
                "tool": self.name,
                "inputs": {"domain": domain},
                "outputs": {
                    "results": [
                        {"type": "email", "value": email, "source": self.name}
                        for email in emails
                    ]
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"domain": domain}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "emailfinder command not found. Install via: pip install emailfinder"}
        except subprocess.TimeoutExpired:
            return {"error": "emailfinder command timed out"}
        except Exception as e:
            self.logger.exception("emailfinder execution failed")
            return {"error": str(e)}

    def _extract_emails(self, text: str) -> list:
        """Extract email addresses using regex."""
        email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return list(set(re.findall(email_regex, text)))
