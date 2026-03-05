import subprocess
import logging
import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    Diagnostic system to verify the readiness of the BBH-AI environment.
    Checks for Docker, API keys, and required security tools.
    
    Returns detailed status for each check to help with troubleshooting.
    """
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.results: Dict[str, Tuple[bool, str]] = {}

    def run_all(self) -> bool:
        """
        Run all health checks. Returns True if all critical checks pass.
        
        Returns:
            True if system is ready for scanning, False otherwise
        """
        print("\n[+] BBH-AI Health Diagnostic Tool")
        print("=" * 50)
        
        checks = [
            ("Docker Sandbox", self.check_docker),
            ("LLM API Keys", self.check_api_keys),
            ("Security Tools", self.check_tools),
            ("Network Connectivity", self.check_network),
        ]
        
        all_passed = True
        for name, check_func in checks:
            print(f"[*] Checking {name}...")
            try:
                status = check_func()
                self.results[name] = (status, "OK" if status else "FAILED")
                if not status:
                    all_passed = False
            except Exception as e:
                self.logger.error(f"Error running health check '{name}': {e}")
                self.results[name] = (False, f"Error: {str(e)}")
                all_passed = False
        
        print("=" * 50)
        if all_passed:
            print("[+] System Status: READY ✓\n")
        else:
            print("[-] System Status: UNREADY (Check errors above) ✗\n")
            self._print_remediation()
            
        return all_passed

    def check_docker(self) -> bool:
        """Check if Docker is available and functional."""
        if not self.config.get('sandbox', {}).get('enabled', True):
            print("    [!] Docker sandbox is disabled in config. Skipping.")
            return True
        
        try:
            result = subprocess.run(
                ["docker", "info"], 
                check=True, 
                capture_output=True,
                timeout=5
            )
            print("    [+] Docker is running and available ✓")
            
            # Check sandbox image
            image = self.config.get('sandbox', {}).get('image', 'bbh/sandbox:latest')
            try:
                res = subprocess.run(
                    ["docker", "image", "inspect", image], 
                    capture_output=True, 
                    check=False,
                    timeout=5
                )
                if res.returncode == 0:
                    print(f"    [+] Sandbox image '{image}' is available locally ✓")
                else:
                    print(f"    [i] Sandbox image '{image}' not found locally. Will pull on first run.")
            except Exception as e:
                self.logger.debug(f"Error checking sandbox image: {e}")
                
            return True
            
        except subprocess.CalledProcessError:
            print("    [!] Docker is NOT running. Please start Docker service.")
            return False
        except FileNotFoundError:
            print("    [!] Docker is NOT installed. Install from: https://docker.com")
            return False
        except subprocess.TimeoutExpired:
            print("    [!] Docker check timed out. Docker may be unresponsive.")
            return False
        except Exception as e:
            print(f"    [!] Docker check failed: {e}")
            return False

    def check_api_keys(self) -> bool:
        """Check for required LLM API keys."""
        keys = {
            "OpenAI": "OPENAI_API_KEY",
            "Anthropic": "ANTHROPIC_API_KEY",
            "Google Gemini": "GOOGLE_API_KEY",
            "DeepSeek": "DEEPSEEK_API_KEY"
        }
        
        found_keys = []
        missing_keys = []
        
        for name, env_var in keys.items():
            if os.getenv(env_var):
                found_keys.append(name)
                print(f"    [+] {name} API key found ✓")
            else:
                missing_keys.append(name)
                print(f"    [-] {name} API key is missing")
        
        if not found_keys:
            print("    [!] CRITICAL: No LLM API keys found. Scan will fail.")
            return False
        
        if found_keys:
            print(f"    [+] At least one LLM provider is configured: {', '.join(found_keys)} ✓")
        
        return True

    def check_tools(self) -> bool:
        """Verify if critical tools are available."""
        # If sandbox is enabled, tools are only needed inside container
        if self.config.get('sandbox', {}).get('enabled', True):
            print("    [i] Tools will be executed in Docker sandbox.")
            print("    [+] Tool verification skipped (sandbox mode enabled) ✓")
            return True
        
        # If sandbox disabled, check for local tools
        essential_tools = {
            "subfinder": "Subdomain enumeration",
            "httpx": "HTTP probing",
            "nuclei": "Vulnerability scanning",
            "nmap": "Port scanning",
        }
        
        missing = []
        found = []
        
        for tool, description in essential_tools.items():
            try:
                # Try running with --version or -h
                result = subprocess.run(
                    [tool, "--version"], 
                    capture_output=True, 
                    timeout=5,
                    check=False
                )
                if result.returncode == 0:
                    found.append(f"{tool} ({description})")
                    print(f"    [+] {tool} is installed ✓")
                else:
                    missing.append(tool)
                    print(f"    [-] {tool} not found")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                missing.append(tool)
                print(f"    [-] {tool} not found")
        
        if found:
            print(f"    [+] Found {len(found)} essential tools")
        
        if missing:
            print(f"    [!] Missing tools: {', '.join(missing)}")
            return False
        
        return True

    def check_network(self) -> bool:
        """Check basic network connectivity."""
        try:
            # Try a quick DNS resolution
            import socket
            socket.gethostbyname('api.openai.com')
            print("    [+] Network connectivity confirmed ✓")
            return True
        except Exception as e:
            print(f"    [!] Network connectivity check failed: {e}")
            print("    [i] You may still be able to run scans if targets are on local network")
            return False  # Non-critical for local targets

    def _print_remediation(self) -> None:
        """Print remediation steps for failed checks."""
        print("\n[*] Remediation Steps:")
        
        if not self.results.get("Docker Sandbox", (False, ""))[0]:
            print("\n  1. Docker Installation:")
            print("     - Visit: https://docs.docker.com/get-docker/")
            print("     - Follow platform-specific installation instructions")
            print("     - Verify: docker info")
        
        if not self.results.get("LLM API Keys", (False, ""))[0]:
            print("\n  2. LLM API Keys Setup:")
            print("     - Create .env file with your API keys:")
            print("       OPENAI_API_KEY=sk-...")
            print("       ANTHROPIC_API_KEY=sk-ant-...")
            print("       GOOGLE_API_KEY=...")
            print("       DEEPSEEK_API_KEY=...")
            print("     - At least ONE provider is required")
        
        if not self.results.get("Security Tools", (False, ""))[0]:
            print("\n  3. Security Tools Installation:")
            print("     - If using sandbox (recommended):")
            print("       docker build -t bbh/sandbox:latest -f sandbox/Dockerfile.sandbox .")
            print("     - Or install tools locally:")
            print("       go install -v github.com/projectdiscovery/subfinder/cmd/subfinder@latest")
            print("       go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest")

    def get_summary(self) -> Dict[str, any]:
        """Return a summary of all checks."""
        return {
            "version": "2.0",
            "results": {k: v[0] for k, v in self.results.items()},
            "overall_status": "READY" if all(v[0] for v in self.results.values()) else "UNREADY"
        }
