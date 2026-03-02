import subprocess
import logging

class DalfoxTool:
    name = "dalfox"
    input_schema = {"file": str, "only_poc": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, file, only_poc="r"):
        self.logger.info(f"Running dalfox on {file}")
        cmd = [
            "dalfox", "file", file,
            "--silence", "--no-color",
            "--only-poc", only_poc,
            "--output", str(self.workspace / "dalfox_raw.txt")
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
            if result.returncode != 0:
                self.logger.error(f"dalfox failed: {result.stderr}")
                return {"error": result.stderr, "findings": []}
            outfile = self.workspace / "dalfox_raw.txt"
            if outfile.exists():
                findings = outfile.read_text().strip().splitlines()
            else:
                findings = []
            self.telemetry.log_tool_call("dalfox", {"file": file}, len(findings))
            return {"findings": findings}
        except subprocess.TimeoutExpired:
            self.logger.error("dalfox timed out")
            return {"error": "timeout", "findings": []}
        except Exception as e:
            self.logger.exception("Unexpected error in dalfox")
            return {"error": str(e), "findings": []}