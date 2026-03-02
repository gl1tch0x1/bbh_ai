import subprocess
import logging
from pathlib import Path


class GospiderTool:
    name = "gospider"
    categories = ["recon"]
    input_schema = {"sites": str, "crawl_depth": int, "concurrent": int}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, sites: str, crawl_depth: int = 5, concurrent: int = 50) -> dict:
        self.logger.info(f"Running gospider on {sites}")
        if not self.workspace:
            self.logger.error("gospider requires a workspace path — workspace is None.")
            return {"error": "workspace not configured", "urls": []}

        output_dir = Path(self.workspace) / "gospider_out"
        output_dir.mkdir(exist_ok=True)
        cmd = [
            "gospider",
            "-S", sites,
            "-d", str(crawl_depth),
            "-c", str(concurrent),
            "-o", str(output_dir),
            "--sitemap", "--robots", "-q",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._timeout, check=False
            )
            if result.returncode != 0:
                self.logger.error(f"gospider failed: {result.stderr.strip()}")
                return {"error": result.stderr.strip(), "urls": []}
            urls: set = set()
            for outfile in output_dir.glob("*"):
                if outfile.is_file():
                    urls.update(
                        line for line in outfile.read_text(encoding='utf-8').strip().splitlines() if line
                    )
            if self.telemetry:
                self.telemetry.log_tool_call("gospider", {"sites": sites}, len(urls))
            self.logger.info(f"gospider discovered {len(urls)} unique URLs")
            return {"urls": list(urls)}
        except subprocess.TimeoutExpired:
            self.logger.error(f"gospider timed out after {self._timeout}s")
            return {"error": "timeout", "urls": []}
        except FileNotFoundError:
            self.logger.error("gospider binary not found. Is it installed?")
            return {"error": "gospider not installed", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in gospider")
            return {"error": str(e), "urls": []}