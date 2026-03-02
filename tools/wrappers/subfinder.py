import subprocess
import logging

class SubfinderTool:
    name = "subfinder"
    input_schema = {"domain": str, "silent": bool}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, domain, silent=True):
        self.logger.info(f"Running subfinder on {domain}")
        cmd = ["subfinder", "-d", domain]
        if silent:
            cmd.append("-silent")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            if result.returncode != 0:
                self.logger.error(f"subfinder failed: {result.stderr}")
                return {"error": result.stderr, "subdomains": []}
            subdomains = result.stdout.strip().splitlines()
            self.telemetry.log_tool_call("subfinder", {"domain": domain}, len(subdomains))
            return {"subdomains": subdomains}
        except subprocess.TimeoutExpired:
            self.logger.error("subfinder timed out")
            return {"error": "timeout", "subdomains": []}
        except Exception as e:
            self.logger.exception("Unexpected error in subfinder")
            return {"error": str(e), "subdomains": []}