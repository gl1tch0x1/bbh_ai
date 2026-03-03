import subprocess
import json
import logging
import os
from pathlib import Path

class SqlmapTool:
    name = "sqlmap"
    categories = ["vuln", "web"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 1800)

    def run(self, url: str, args: list = None) -> dict:
        self.logger.info(f"Running sqlmap on {url}...")
        try:
            # Default args: --batch --random-agent --level=1 --risk=1
            cmd = ["sqlmap", "-u", url, "--batch", "--random-agent", "--level", "1", "--risk", "1"]
            if args: cmd.extend(args)
            
            # Sqlmap can output JSON to a specific directory using --output-dir
            output_dir = self.workspace / "sqlmap_results"
            cmd.extend(["--output-dir", str(output_dir)])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            # Sqlmap results are stored in output_dir/domain/log or similar
            # For this wrapper, we'll summarize the stdout and look for "vulnerable" keywords
            vulnerable = "is vulnerable" in result.stdout or "back-end DBMS is" in result.stdout
            
            output = {
                "tool": self.name,
                "inputs": {"url": url, "args": args},
                "outputs": {
                    "results": [
                        {
                            "type": "sql_injection",
                            "value": url,
                            "source": self.name,
                            "metadata": {"vulnerable": vulnerable}
                        }
                    ] if vulnerable else [],
                    "raw": result.stdout
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"url": url}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "sqlmap command not found. See https://sqlmap.org/"}
        except subprocess.TimeoutExpired:
            return {"error": "sqlmap command timed out"}
        except Exception as e:
            return {"error": str(e)}
