import subprocess
import json
import logging
import os
from pathlib import Path

class TestsslTool:
    name = "testssl"
    categories = ["vuln", "hosts"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, target: str) -> dict:
        self.logger.info(f"Running testssl.sh on {target}...")
        output_file = self.workspace / "testssl_results.json"
        
        try:
            # Usage: testssl.sh --jsonfile results.json target
            # Assuming testssl.sh is in the PATH or we use a wrapper
            cmd = ["testssl.sh", "--jsonfile", str(output_file), target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    try:
                        data = json.load(f)
                        # Normalize testssl results (it's a list of dictionaries)
                        for item in data:
                            if item.get('severity') not in ['OK', 'INFO', 'LOW']:
                                findings.append({
                                    "type": "ssl_vuln",
                                    "value": item.get('id', 'unknown'),
                                    "source": self.name,
                                    "metadata": item
                                })
                    except json.JSONDecodeError:
                        pass
            
            output = {
                "tool": self.name,
                "inputs": {"target": target},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode in [0, 1] else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"target": target}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "testssl.sh command not found. See https://github.com/drwetter/testssl.sh"}
        except subprocess.TimeoutExpired:
            return {"error": "testssl.sh command timed out"}
        except Exception as e:
            return {"error": str(e)}
