import subprocess
import json
import logging
import os
from pathlib import Path

class NoseyparkerTool:
    name = "noseyparker"
    categories = ["github", "vuln"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 600)

    def run(self, source: str) -> dict:
        """source can be a local path or a git URL."""
        self.logger.info(f"Running noseyparker on {source}...")
        report_file = self.workspace / "noseyparker_report.json"
        datastore = self.workspace / "noseyparker_db"
        
        try:
            # Usage: noseyparker scan --datastore <db> <source>
            # Then: noseyparker report --datastore <db> --json > report.json
            scan_cmd = ["noseyparker", "scan", "--datastore", str(datastore), source]
            subprocess.run(scan_cmd, capture_output=True, text=True, timeout=self._timeout)
            
            report_cmd = ["noseyparker", "report", "--datastore", str(datastore), "--json"]
            result = subprocess.run(report_cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    # Noseyparker returns a list of finding objects
                    for item in data:
                        findings.append({
                            "type": "secret",
                            "value": item.get('match_content', ''),
                            "source": self.name,
                            "metadata": item
                        })
                except json.JSONDecodeError:
                    pass
            
            output = {
                "tool": self.name,
                "inputs": {"source": source},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "error"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"source": source}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "noseyparker command not found. See https://github.com/praetorian-inc/noseyparker"}
        except subprocess.TimeoutExpired:
            return {"error": "noseyparker command timed out"}
        except Exception as e:
            return {"error": str(e)}
