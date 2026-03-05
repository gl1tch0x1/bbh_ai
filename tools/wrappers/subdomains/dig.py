import logging
import subprocess
from typing import Any, Dict, Optional
from pathlib import Path

class DigTool:
    """
    Checks for misconfigured DNS zone transfers.
    """
    name = "dig"
    categories = ["subdomains", "recon"]
    input_schema = {"domain": str, "nameserver": Optional[str]}

    def __init__(self, config: Dict[str, Any], workspace: Path, telemetry: Any):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, domain: str, nameserver: str = "") -> Dict[str, Any]:
        """Run dig AXFR check for DNS zone transfers."""
        try:
            cmd = ["dig", "+nocmd", "+noall", "+answer", "axfr", domain]
            if nameserver:
                cmd.append(f"@{nameserver}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "domain": domain,
                "nameserver": nameserver,
                "vulnerable": "Transfer authorized" in result.stdout
            }
        except subprocess.TimeoutExpired:
            self.logger.error(f"dig timeout for {domain}")
            return {"success": False, "error": "Timeout", "domain": domain}
        except Exception as e:
            self.logger.error(f"dig error: {e}")
            return {"success": False, "error": str(e), "domain": domain}
