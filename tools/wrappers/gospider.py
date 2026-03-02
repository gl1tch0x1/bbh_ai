import subprocess
import logging
from pathlib import Path

class GospiderTool:
    name = "gospider"
    input_schema = {"sites": str, "depth": int, "concurrent": int}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, sites, depth=5, concurrent=50):
        self.logger.info(f"Running gospider on {sites}")
        output_dir = self.workspace / "gospider_out"
        output_dir.mkdir(exist_ok=True)
        cmd = [
            "gospider",
            "-S", sites,
            "-d", str(depth),
            "-c", str(concurrent),
            "-o", str(output_dir),
            "--sitemap", "--robots", "-q"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
            if result.returncode != 0:
                self.logger.error(f"gospider failed: {result.stderr}")
                return {"error": result.stderr, "urls": []}
            urls = set()
            for outfile in output_dir.glob("*"):
                if outfile.is_file():
                    urls.update(outfile.read_text().strip().splitlines())
            self.telemetry.log_tool_call("gospider", {"sites": sites}, len(urls))
            return {"urls": list(urls)}
        except subprocess.TimeoutExpired:
            self.logger.error("gospider timed out")
            return {"error": "timeout", "urls": []}
        except Exception as e:
            self.logger.exception("Unexpected error in gospider")
            return {"error": str(e), "urls": []}