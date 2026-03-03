import subprocess
import json
import logging
import os
from pathlib import Path

class EnumerepoTool:
    name = "enumerepo"
    categories = ["osint", "github", "discovery"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 180)

    def run(self, target: str) -> dict:
        """target can be a GitHub username or org."""
        self.logger.info(f"Running enumerepo on {target}...")
        output_file = self.workspace / f"enumerepo_{target}.json"
        
        try:
            # Usage: enumerepo -u target -o output.json
            token = self.config.get('github', {}).get('github_token')
            cmd = ["enumerepo", "-u", target, "-o", str(output_file)]
            if token:
                cmd.extend(["-t", token])
                
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            repos = []
            if output_file.exists():
                with open(output_file, 'r') as f:
                    try:
                        repos = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            output = {
                "tool": self.name,
                "inputs": {"target": target},
                "outputs": {
                    "results": [
                        {"type": "github_repo", "value": repo.get('url', ''), "source": self.name, "metadata": repo}
                        for repo in repos if isinstance(repo, dict)
                    ]
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"target": target}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "enumerepo command not found. See https://github.com/rix4uni/enumerepo"}
        except subprocess.TimeoutExpired:
            return {"error": "enumerepo command timed out"}
        except Exception as e:
            return {"error": str(e)}
