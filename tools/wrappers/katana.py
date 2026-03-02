import subprocess
import logging


class KatanaTool:
    name = "katana"
    categories = ["recon"]
    # Renamed 'list' → 'target_list', 'depth' → 'crawl_depth' to avoid shadowing Python built-ins
    input_schema = {"target_list": str, "crawl_depth": int, "jc": bool, "aff": bool}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, target_list: str = None, crawl_depth: int = 5, jc: bool = True, aff: bool = True) -> dict:
        self.logger.info(f"Running katana on {target_list}")
        cmd = ["katana", "-silent"]
        if target_list:
            cmd.extend(["-list", target_list])
        if crawl_depth:
            cmd.extend(["-d", str(crawl_depth)])
        if jc:
            cmd.append("-jc")
        if aff:
            cmd.append("-aff")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"katana failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "urls": []}
            urls = [u for u in result.stdout.strip().splitlines() if u]
            if self.telemetry:
                self.telemetry.log_tool_call("katana", {"list": target_list}, len(urls))
            self.logger.info(f"katana crawled {len(urls)} URLs")
            return {"urls": urls}
        except subprocess.TimeoutExpired:
            self.logger.error(f"katana timed out after {self._timeout}s")
            return {"error": "timeout", "urls": []}
        except FileNotFoundError:
            self.logger.error("katana binary not found. Is it installed?")
            return {"error": "katana not installed", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in katana")
            return {"error": str(e), "urls": []}