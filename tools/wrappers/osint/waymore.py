import subprocess
import logging
from pathlib import Path


class WaymoreTool:
    name = "waymore"
    categories = ["recon"]
    input_schema = {"domain": str, "mode": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 180)

    def run(self, domain: str, mode: str = "U") -> dict:
        self.logger.info(f"Running waymore on {domain}")
        if not self.workspace:
            self.logger.error("waymore requires a workspace path — workspace is None.")
            return {"error": "workspace not configured", "urls": []}

        # Use absolute path for output to avoid CWD-relative file loss
        output_file = Path(self.workspace) / "waymore_output.txt"
        cmd = ["waymore", "-i", domain, "-mode", mode, "-oU", str(output_file)]

        try:
            result = subprocess.run(
                cmd, cwd=str(self.workspace),
                capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"waymore failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "urls": []}
            if output_file.exists():
                urls = [u for u in output_file.read_text(encoding='utf-8').strip().splitlines() if u]
            else:
                urls = []
            if self.telemetry:
                self.telemetry.log_tool_call("waymore", {"domain": domain}, len(urls))
            self.logger.info(f"waymore collected {len(urls)} URLs for {domain}")
            return {"urls": urls}
        except subprocess.TimeoutExpired:
            self.logger.error(f"waymore timed out after {self._timeout}s")
            return {"error": "timeout", "urls": []}
        except FileNotFoundError:
            self.logger.error("waymore not found. Is it installed?")
            return {"error": "waymore not installed", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in waymore")
            return {"error": str(e), "urls": []}