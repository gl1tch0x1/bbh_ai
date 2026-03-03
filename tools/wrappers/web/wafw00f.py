import subprocess
import json
import logging
from pathlib import Path

class Wafw00fTool:
    name = "wafw00f"
    categories = ["web", "recon", "vuln"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, url: str) -> dict:
        self.logger.info(f"Running wafw00f on {url}...")
        output_file = self.workspace / "wafw00f_results.json"
        
        try:
            # Usage: wafw00f <url> -o results.json
            cmd = ["wafw00f", url, "-o", str(output_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    try:
                        data = json.load(f)
                        # Normalize wafw00f results
                        for item in data:
                            findings.append({
                                "type": "waf_detection",
                                "value": item.get('waf', 'unknown'),
                                "source": self.name,
                                "metadata": item
                            })
                    except json.JSONDecodeError:
                        pass
            
            output = {
                "tool": self.name,
                "inputs": {"url": url},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"url": url}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "wafw00f command not found. See https://github.com/EnableSecurity/wafw00f"}
        except subprocess.TimeoutExpired:
            return {"error": "wafw00f command timed out"}
        except Exception as e:
            return {"error": str(e)}
