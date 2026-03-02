import subprocess
import logging

class KatanaTool:
    name = "katana"
    input_schema = {"list": str, "depth": int, "jc": bool, "aff": bool}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, list=None, depth=5, jc=True, aff=True):
        self.logger.info(f"Running katana on {list}")
        cmd = ["katana", "-silent"]
        if list:
            cmd.extend(["-list", list])
        if depth:
            cmd.extend(["-d", str(depth)])
        if jc:
            cmd.append("-jc")
        if aff:
            cmd.append("-aff")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
            if result.returncode != 0:
                self.logger.error(f"katana failed: {result.stderr}")
                return {"error": result.stderr, "urls": []}
            urls = result.stdout.strip().splitlines()
            self.telemetry.log_tool_call("katana", {"list": list}, len(urls))
            return {"urls": urls}
        except subprocess.TimeoutExpired:
            self.logger.error("katana timed out")
            return {"error": "timeout", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in katana")
            return {"error": str(e), "urls": []}