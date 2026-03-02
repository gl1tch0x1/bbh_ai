import subprocess
import logging
import json


class HttpxTool:
    name = "httpx"
    categories = ["recon"]
    # Renamed 'list' → 'host_list' to avoid shadowing Python built-in
    input_schema = {"host_list": str, "probe": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 120)

    def run(self, host_list: str = None, probe: str = None) -> dict:
        self.logger.info(f"Running httpx on {host_list or probe}")
        cmd = ["httpx", "-silent"]
        if host_list:
            cmd.extend(["-l", host_list])
        if probe:
            cmd.extend(["-u", probe])
        cmd.extend(["-status-code", "-title", "-tech-detect", "-json"])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"httpx failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "results": []}
            results = []
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    self.logger.debug(f"httpx: skipping non-JSON line: {line[:80]}")
            if self.telemetry:
                self.telemetry.log_tool_call("httpx", {"input": host_list or probe}, len(results))
            self.logger.info(f"httpx probed {len(results)} live hosts")
            return {"results": results}
        except subprocess.TimeoutExpired:
            self.logger.error(f"httpx timed out after {self._timeout}s")
            return {"error": "timeout", "results": []}
        except FileNotFoundError:
            self.logger.error("httpx binary not found. Is it installed?")
            return {"error": "httpx not installed", "results": []}
        except Exception as e:
            self.logger.exception("Unexpected error in httpx")
            return {"error": str(e), "results": []}