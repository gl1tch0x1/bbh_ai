import subprocess
import json
import logging
import os
from pathlib import Path

class AnalyticsrelationshipsTool:
    name = "analyticsrelationships"
    categories = ["subdomains", "osint", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, url: str) -> dict:
        self.logger.info(f"Running AnalyticsRelationships on {url}...")
        try:
            # Usage: python3 analyticsrelationships.py -u url
            cmd = ["python3", "analyticsrelationships.py", "-u", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            domains = []
            if result.stdout.strip():
                # Tool outputs discovered domains to stdout
                for line in result.stdout.splitlines():
                    if line.strip() and "." in line:
                        domains.append({"type": "domain_related", "value": line.strip(), "source": self.name})

            output = {
                "tool": self.name,
                "inputs": {"url": url},
                "outputs": {
                    "results": domains,
                    "count": len(domains)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"url": url}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "analyticsrelationships.py not found. See https://github.com/JosueEncinar/AnalyticsRelationships"}
        except subprocess.TimeoutExpired:
            return {"error": "analyticsrelationships command timed out"}
        except Exception as e:
            return {"error": str(e)}
