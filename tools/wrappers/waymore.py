import subprocess
import logging
from pathlib import Path

class WaymoreTool:
    name = "waymore"
    input_schema = {"domain": str, "mode": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, domain, mode="U"):
        self.logger.info(f"Running waymore on {domain}")
        cmd = ["waymore", "-i", domain, "-mode", mode, "-oU", "waymore_output.txt"]
        cwd = self.workspace
        try:
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180, check=False)
            if result.returncode != 0:
                self.logger.error(f"waymore failed: {result.stderr}")
                return {"error": result.stderr, "urls": []}
            output_file = cwd / "waymore_output.txt"
            if output_file.exists():
                urls = output_file.read_text().strip().splitlines()
            else:
                urls = []
            self.telemetry.log_tool_call("waymore", {"domain": domain}, len(urls))
            return {"urls": urls}
        except subprocess.TimeoutExpired:
            self.logger.error("waymore timed out")
            return {"error": "timeout", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in waymore")
            return {"error": str(e), "urls": []}