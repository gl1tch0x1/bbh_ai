import subprocess
import logging
import os
from pathlib import Path
from typing import Dict, List

class HealthChecker:
    """
    Diagnostic system to verify the readiness of the BBH-AI environment.
    Checks for Docker, API keys, and required security tools.
    """
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def run_all(self) -> bool:
        """Run all health checks. Returns True if all critical checks pass."""
        print("\n[+] BBH-AI Health Diagnostic Tool")
        print("=" * 40)
        
        checks = [
            ("Docker Sandbox", self.check_docker),
            ("LLM API Keys", self.check_api_keys),
            ("Security Tools", self.check_tools)
        ]
        
        all_passed = True
        for name, check_func in checks:
            print(f"[*] Checking {name}...")
            if not check_func():
                all_passed = False
        
        print("=" * 40)
        if all_passed:
            print("[+] System Status: READY\n")
        else:
            print("[-] System Status: UNREADY (Check errors above)\n")
            
        return all_passed

    def check_docker(self) -> bool:
        if not self.config.get('sandbox', {}).get('enabled', True):
            print("    [!] Docker sandbox is disabled in config. Skipping.")
            return True
        
        try:
            subprocess.run(["docker", "info"], check=True, capture_output=True)
            print("    [+] Docker is running and available.")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("    [!] Docker is NOT running or NOT installed. Essential for sandboxing.")
            return False

    def check_api_keys(self) -> bool:
        keys = {
            "OpenAI": "OPENAI_API_KEY",
            "Anthropic": "ANTHROPIC_API_KEY",
            "Google Gemini": "GOOGLE_API_KEY",
            "DeepSeek": "DEEPSEEK_API_KEY"
        }
        
        found_any = False
        for name, env_var in keys.items():
            if os.getenv(env_var):
                print(f"    [+] {name} API key found.")
                found_any = True
            else:
                print(f"    [-] {name} API key is missing.")
        
        if not found_any:
            print("    [!] CRITICAL: No LLM API keys found. Scan will fail.")
            return False
        return True

    def check_tools(self) -> bool:
        """Verify if critical tools are available in the system path or sandbox."""
        # This is a simplified check for the host if sandbox is disabled,
        # or a general check for critical tools.
        essential_tools = ["subfinder", "httpx", "nuclei", "nmap", "interactsh-client"]
        
        missing = []
        for tool in essential_tools:
            # Handle interactsh-client vs interactsh naming
            cmd = tool
            try:
                subprocess.run([cmd, "--version"], capture_output=True, check=False)
                print(f"    [+] {tool} is installed.")
            except FileNotFoundError:
                missing.append(tool)
        
        if missing:
            print(f"    [-] Missing essential tools: {', '.join(missing)}")
            if self.config.get('sandbox', {}).get('enabled', True):
                print("    [i] Note: These tools will be run inside Docker.")
                return True
            return False
        return True
