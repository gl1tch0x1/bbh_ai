import subprocess
import logging
from pathlib import Path


class DalfoxTool:
    name = "dalfox"
    categories = ["exploit"]
    input_schema = {"file": str, "only_poc": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, file: str, only_poc: str = "r") -> dict:
        self.logger.info(f"Running dalfox on {file}")
        if not self.workspace:
            self.logger.error("dalfox requires a workspace path — workspace is None.")
            return {"error": "workspace not configured", "findings": []}

        output_file = Path(self.workspace) / "dalfox_raw.txt"
        cmd = [
            "dalfox", "file", file,
            "--silence", "--no-color",
            "--only-poc", only_poc,
            "--output", str(output_file),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"dalfox failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "findings": []}
            if output_file.exists():
                findings = [l for l in output_file.read_text(encoding='utf-8').strip().splitlines() if l]
            else:
                findings = []
            if self.telemetry:
                self.telemetry.log_tool_call("dalfox", {"file": file}, len(findings))
            self.logger.info(f"dalfox found {len(findings)} XSS findings")
            return {"findings": findings}
        except subprocess.TimeoutExpired:
            self.logger.error(f"dalfox timed out after {self._timeout}s")
            return {"error": "timeout", "findings": []}
        except FileNotFoundError:
            self.logger.error("dalfox binary not found. Is it installed?")
            return {"error": "dalfox not installed", "findings": []}
        except Exception as e:
            self.logger.exception("Unexpected error in dalfox")
            return {"error": str(e), "findings": []}