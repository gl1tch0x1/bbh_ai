import subprocess
import json
import logging
import os
from pathlib import Path

class CloudEnumTool:
    name = "cloud_enum"
    categories = ["osint", "cloud", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, keyword: str) -> dict:
        self.logger.info(f"Running cloud_enum on {keyword}...")
        output_file = self.workspace / f"cloud_enum_{keyword}.json"
        
        try:
            # Usage: python3 cloud_enum.py -k keyword -l logfile.json (some versions use -l or -o)
            # Assuming standard cloud_enum.py usage or wrapper
            cmd = ["cloud_enum", "-k", keyword, "-j", str(output_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    try:
                        data = json.load(f)
                        # Normalize cloud_enum nested structure
                        for platform, assets in data.items():
                            for asset in assets:
                                findings.append({
                                    "type": "cloud_asset",
                                    "value": asset,
                                    "source": self.name,
                                    "metadata": {"platform": platform}
                                })
                    except json.JSONDecodeError:
                        pass
            
            output = {
                "tool": self.name,
                "inputs": {"keyword": keyword},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"keyword": keyword}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "cloud_enum command not found. See https://github.com/initstring/cloud_enum"}
        except subprocess.TimeoutExpired:
            return {"error": "cloud_enum command timed out"}
        except Exception as e:
            return {"error": str(e)}
