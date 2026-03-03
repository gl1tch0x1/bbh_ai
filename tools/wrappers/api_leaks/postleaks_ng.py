import subprocess
import json
import logging
import re
from pathlib import Path

class PostleaksNgTool:
    name = "postleaks-ng"
    categories = ["osint", "api_leaks"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, keyword: str) -> dict:
        self.logger.info(f"Running postleaks-ng on keyword: {keyword}...")
        try:
            # Usage: postleaks-ng search -q "keyword"
            cmd = ["postleaks-ng", "search", "-q", keyword]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            # Postleaks-ng outputs results to stdout, let's try to extract JSON if available
            findings = []
            if result.stdout.strip():
                # Attempt to parse output lines as possible secrets or links
                findings = [{"raw_line": line} for line in result.stdout.splitlines() if line.strip()]

            output = {
                "tool": self.name,
                "inputs": {"keyword": keyword},
                "outputs": {
                    "results": [
                        {"type": "api_leak", "value": f.get('raw_line', keyword), "source": self.name, "metadata": f}
                        for f in findings
                    ]
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"keyword": keyword}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "postleaks-ng command not found. See https://github.com/G0V1ND-S/postleaks-ng"}
        except subprocess.TimeoutExpired:
            return {"error": "postleaks-ng command timed out"}
        except Exception as e:
            return {"error": str(e)}
