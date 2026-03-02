import subprocess
import logging

class NucleiTool:
    name = "nuclei"
    input_schema = {"target": str, "list": bool, "templates": str, "output": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, target, list=False, templates=None, output=None):
        self.logger.info(f"Running nuclei on {target}")
        cmd = ["nuclei", "-silent"]
        if list:
            cmd.extend(["-l", target])
        else:
            cmd.extend(["-u", target])
        if templates:
            cmd.extend(["-t", templates])
        if output:
            cmd.extend(["-o", output])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
            if result.returncode != 0:
                self.logger.error(f"nuclei failed: {result.stderr}")
                return {"error": result.stderr, "findings": []}
            findings = result.stdout.strip().splitlines()
            self.telemetry.log_tool_call("nuclei", {"target": target}, len(findings))
            return {"findings": findings}
        except subprocess.TimeoutExpired:
            self.logger.error("nuclei timed out")
            return {"error": "timeout", "findings": []}
        except Exception as e:
            self.logger.exception("Unexpected error in nuclei")
            return {"error": str(e), "findings": []}