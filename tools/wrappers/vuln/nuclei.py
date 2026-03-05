import json
import subprocess
import logging


class NucleiTool:
    name = "nuclei"
    categories = ["exploit", "recon"]
    # Renamed 'list' → 'target_list' to avoid shadowing Python built-in
    input_schema = {"target": str, "target_list": bool, "templates": str, "output": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, target: str, target_list: bool = False, templates: str = None, output: str = None) -> dict:
        self.logger.info(f"Running nuclei on {target}")
        cmd = ["nuclei", "-silent", "-jsonl"]
        if target_list:
            cmd.extend(["-l", target])
        else:
            cmd.extend(["-u", target])
        if templates:
            cmd.extend(["-t", templates])
        if output:
            cmd.extend(["-o", output])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"nuclei failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "findings": []}
            findings = []
            if result.stdout.strip():
                for line in result.stdout.splitlines():
                    if line.strip():
                        try:
                            findings.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            output = {
                "tool": self.name,
                "inputs": {"target": target, "templates": templates},
                "outputs": {
                    "results": [
                        {"type": "vuln", "value": target, "source": self.name, "metadata": f}
                        for f in findings
                    ],
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }

            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"target": target}, output)
            
            return output
        except subprocess.TimeoutExpired:
            self.logger.error(f"nuclei timed out after {self._timeout}s")
            return {"error": "timeout", "findings": []}
        except FileNotFoundError:
            self.logger.error("nuclei binary not found. Is it installed?")
            return {"error": "nuclei not installed", "findings": []}
        except Exception as e:
            self.logger.exception("Unexpected error in nuclei")
            return {"error": str(e), "findings": []}