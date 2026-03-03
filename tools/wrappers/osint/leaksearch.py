import subprocess
import json
import logging
import os
from pathlib import Path

class LeakSearchTool:
    name = "leaksearch"
    categories = ["osint", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, keyword: str) -> dict:
        self.logger.info(f"Running leaksearch on {keyword}...")
        output_file = self.workspace / f"leaksearch_{keyword}.json"
        
        try:
            # Usage: python3 leaksearch.py -k keyword -o json -f <output>
            # Assuming leaksearch.py is in the PATH or we use a wrapper script
            cmd = ["leaksearch", "-k", keyword, "-o", "json", "-f", str(output_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    try:
                        findings = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            output = {
                "tool": self.name,
                "inputs": {"keyword": keyword},
                "outputs": {
                    "results": [
                        {"type": "leak", "value": f.get('email', keyword), "source": self.name, "metadata": f}
                        for f in findings if isinstance(f, dict)
                    ],
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"keyword": keyword}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "leaksearch command not found. See https://github.com/JoelGMSec/LeakSearch"}
        except subprocess.TimeoutExpired:
            return {"error": "leaksearch command timed out"}
        except Exception as e:
            return {"error": str(e)}
