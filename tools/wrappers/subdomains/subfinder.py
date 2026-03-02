import subprocess
import logging


class SubfinderTool:
    name = "subfinder"
    categories = ["recon"]
    input_schema = {"domain": str, "silent": bool}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 60)

    def run(self, domain: str, silent: bool = True) -> dict:
        self.logger.info(f"Running subfinder on {domain}")
        cmd = ["subfinder", "-d", domain]
        if silent:
            cmd.append("-silent")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"subfinder failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "subdomains": []}
            subdomains = [s for s in result.stdout.strip().splitlines() if s]
            if self.telemetry:
                self.telemetry.log_tool_call("subfinder", {"domain": domain}, len(subdomains))
            self.logger.info(f"subfinder found {len(subdomains)} subdomains for {domain}")
            return {"subdomains": subdomains}
        except subprocess.TimeoutExpired:
            self.logger.error(f"subfinder timed out after {self._timeout}s")
            return {"error": "timeout", "subdomains": []}
        except FileNotFoundError:
            self.logger.error("subfinder binary not found. Is it installed?")
            return {"error": "subfinder not installed", "subdomains": []}
        except Exception as e:
            self.logger.exception("Unexpected error in subfinder")
            return {"error": str(e), "subdomains": []}