import subprocess
import json
import logging
import os
from pathlib import Path

class CmseekTool:
    name = "cmseek"
    categories = ["web", "recon"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, url: str) -> dict:
        self.logger.info(f"Running CMSeeK on {url}...")
        try:
            # Usage: python3 cmseek.py -u url --batch --json-output
            # CMSeeK stores results in Result/<domain>/cms.json
            cmd = ["python3", "cmseek.py", "-u", url, "--batch", "--follow-redirect"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            # CMSeeK is a bit tricky with output paths, we usually have to find it in Result/
            # For this wrapper, we'll try to find the newest JSON in Result/
            cms_info = self._find_latest_result(url)
            
            output = {
                "tool": self.name,
                "inputs": {"url": url},
                "outputs": {
                    "results": [
                        {"type": "cms_detection", "value": url, "source": self.name, "metadata": cms_info}
                    ] if cms_info else []
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"url": url}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "cmseek script not found. See https://github.com/Tuhinshubhra/CMSeeK"}
        except subprocess.TimeoutExpired:
            return {"error": "cmseek command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _find_latest_result(self, url: str) -> dict:
        # Placeholder for CMSeeK Result/ folder logic
        return {}
