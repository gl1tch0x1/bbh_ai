import subprocess
import json
import logging
import re
from pathlib import Path

class SwaggerspyTool:
    name = "swaggerspy"
    categories = ["osint", "api_leaks"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, keyword: str) -> dict:
        self.logger.info(f"Running swaggerspy on keyword: {keyword}...")
        try:
            # Usage: python3 swaggerspy.py -s "keyword" --json
            cmd = ["swaggerspy", "-s", keyword, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                try:
                    findings = json.loads(result.stdout)
                except json.JSONDecodeError:
                    # Basic extraction from text if JSON flag is not supported
                    findings = [{"raw_line": line} for line in result.stdout.splitlines() if line.strip()]

            output = {
                "tool": self.name,
                "inputs": {"keyword": keyword},
                "outputs": {
                    "results": [
                        {"type": "swagger_leak", "value": f.get('url', keyword), "source": self.name, "metadata": f}
                        for f in findings
                    ]
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"keyword": keyword}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "swaggerspy command not found. See https://github.com/calumhalpin/swaggerspy"}
        except subprocess.TimeoutExpired:
            return {"error": "swaggerspy command timed out"}
        except Exception as e:
            return {"error": str(e)}
