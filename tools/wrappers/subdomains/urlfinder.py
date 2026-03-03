import subprocess
import json
import logging
from pathlib import Path

class UrlfinderTool:
    name = "urlfinder"
    categories = ["subdomains", "web", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 300)

    def run(self, domain: str) -> dict:
        self.logger.info(f"Running urlfinder on {domain}...")
        output_file = self.workspace / f"urlfinder_{domain}.json"
        
        try:
            # Usage: urlfinder -d domain.com -o results.json
            cmd = ["urlfinder", "-d", domain, "-o", str(output_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            findings = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    try:
                        data = json.load(f)
                        # Normalize urlfinder results (subdomains and urls)
                        for item in data:
                            findings.append({
                                "type": "asset",
                                "value": item.get('url', item.get('subdomain', '')),
                                "source": self.name,
                                "metadata": item
                            })
                    except json.JSONDecodeError:
                        pass
            
            output = {
                "tool": self.name,
                "inputs": {"domain": domain},
                "outputs": {
                    "results": findings,
                    "count": len(findings)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"domain": domain}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "urlfinder command not found. See https://github.com/projectdiscovery/urlfinder"}
        except subprocess.TimeoutExpired:
            return {"error": "urlfinder command timed out"}
        except Exception as e:
            return {"error": str(e)}
