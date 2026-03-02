import subprocess
import logging

class GauTool:
    name = "gau"
    input_schema = {"domain": str, "subs": bool, "o": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, domain, subs=True, output=None):
        self.logger.info(f"Running gau on {domain}")
        cmd = ["gau"]
        if subs:
            cmd.append("--subs")
        cmd.append(domain)
        if output:
            cmd.extend(["--o", output])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
            if result.returncode != 0:
                self.logger.error(f"gau failed: {result.stderr}")
                return {"error": result.stderr, "urls": []}
            urls = result.stdout.strip().splitlines()
            self.telemetry.log_tool_call("gau", {"domain": domain}, len(urls))
            return {"urls": urls}
        except subprocess.TimeoutExpired:
            self.logger.error("gau timed out")
            return {"error": "timeout", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in gau")
            return {"error": str(e), "urls": []}