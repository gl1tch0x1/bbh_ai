import subprocess
import logging
import json

class HttpxTool:
    name = "httpx"
    input_schema = {"list": str, "probe": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, list=None, probe=None):
        self.logger.info(f"Running httpx on {list or probe}")
        cmd = ["httpx", "-silent"]
        if list:
            cmd.extend(["-l", list])
        if probe:
            cmd.extend(["-u", probe])
        cmd.extend(["-status-code", "-title", "-tech-detect", "-json"])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
            if result.returncode != 0:
                self.logger.error(f"httpx failed: {result.stderr}")
                return {"error": result.stderr, "results": []}
            lines = result.stdout.strip().splitlines()
            results = []
            for line in lines:
                try:
                    results.append(json.loads(line))
                except:
                    pass
            self.telemetry.log_tool_call("httpx", {"input": list or probe}, len(results))
            return {"results": results}
        except subprocess.TimeoutExpired:
            self.logger.error("httpx timed out")
            return {"error": "timeout", "results": []}
        except Exception as e:
            self.logger.exception("Unexpected error in httpx")
            return {"error": str(e), "results": []}