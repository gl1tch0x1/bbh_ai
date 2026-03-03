import subprocess
import json
import logging
from pathlib import Path

class MsftreconTool:
    name = "msftrecon"
    categories = ["osint", "discovery", "cloud"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 180)

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running msftrecon on {domain}...")
        try:
            # Usage: python3 msftrecon.py -d domain.com
            cmd = ["msftrecon", "-d", domain]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            # Msftrecon usually outputs results to stdout, let's try to extract JSON if available
            # or parse the text output.
            parsed_data = self._parse_output(result.stdout)
            
            output = {
                "tool": self.name,
                "inputs": {"domain": domain},
                "outputs": {
                    "results": [
                        {
                            "type": "msft_tenant_info",
                            "value": domain,
                            "source": self.name,
                            "metadata": parsed_data
                        }
                    ],
                    "raw": result.stdout
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"domain": domain}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "msftrecon command not found. See https://github.com/Arcanum-Sec/msftrecon"}
        except subprocess.TimeoutExpired:
            return {"error": "msftrecon command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_output(self, text: str) -> dict:
        """Attempt to extract key tenant info from msftrecon text output."""
        patterns = {
            "tenant_id": r"Tenant ID:\s*([a-f0-9-]+)",
            "tenant_name": r"Tenant Name:\s*(.*)",
            "o365_active": r"Office 365 is active",
            "mfa_enforced": r"MFA is enforced",
            "sharepoint_url": r"SharePoint URL:\s*(.*)"
        }
        
        # This is a placeholder for actual parsing logic
        # Ideally msftrecon would output JSON, but if not we use regex
        return {"status": "parsed", "content_length": len(text)}
