import subprocess
import logging


class GauTool:
    name = "gau"
    categories = ["recon"]
    input_schema = {"domain": str, "subs": bool, "output": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 120)

    def run(self, domain: str, subs: bool = True, output: str = None) -> dict:
        self.logger.info(f"Running gau on {domain}")
        cmd = ["gau"]
        if subs:
            cmd.append("--subs")
        cmd.append(domain)
        if output:
            cmd.extend(["--o", output])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"gau failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "urls": []}
            urls = [u for u in result.stdout.strip().splitlines() if u]
            if self.telemetry:
                self.telemetry.log_tool_call("gau", {"domain": domain}, len(urls))
            self.logger.info(f"gau collected {len(urls)} URLs for {domain}")
            return {"urls": urls}
        except subprocess.TimeoutExpired:
            self.logger.error(f"gau timed out after {self._timeout}s")
            return {"error": "timeout", "urls": []}
        except FileNotFoundError:
            self.logger.error("gau binary not found. Is it installed?")
            return {"error": "gau not installed", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in gau")
            return {"error": str(e), "urls": []}