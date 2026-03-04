#!/usr/bin/env python3
"""
BBH-AI Sandbox Diagnostics
Comprehensive diagnostic tool for sandbox initialization issues
"""

import subprocess
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def log(msg: str, level: str = "INFO"):
    icons = {
        "ERROR": f"{Colors.RED}✗{Colors.RESET}",
        "OK": f"{Colors.GREEN}✓{Colors.RESET}",
        "WARN": f"{Colors.YELLOW}⚠{Colors.RESET}",
        "INFO": f"{Colors.BLUE}ℹ{Colors.RESET}",
    }
    print(f"{icons.get(level, '')} {msg}")

def run_cmd(cmd: str) -> Tuple[bool, str]:
    """Run a command and return (success, output)"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timeout"
    except Exception as e:
        return False, str(e)

def check_docker() -> bool:
    """Check if Docker is installed and running"""
    log("Checking Docker installation...", "INFO")
    
    success, output = run_cmd("docker --version")
    if not success:
        log("Docker not found", "ERROR")
        return False
    
    log(f"Docker available: {output.strip()}", "OK")
    
    # Check if daemon is running
    success, output = run_cmd("docker ps")
    if not success:
        log("Docker daemon not running", "ERROR")
        return False
    
    log("Docker daemon is running", "OK")
    return True

def check_image() -> bool:
    """Check if bbh-ai-unified image exists"""
    log("Checking Docker image: bbh-ai-unified", "INFO")
    
    success, output = run_cmd("docker images | grep bbh-ai-unified")
    if not success:
        log("Image NOT found - rebuild required", "WARN")
        log("Run: python rebuild_docker.py OR docker build -t bbh-ai-unified -f sandbox/Dockerfile.sandbox .", "INFO")
        return False
    
    log("Image found", "OK")
    return True

def check_containers() -> Dict[str, Any]:
    """Check for existing/failing containers"""
    log("Checking for existing containers...", "INFO")
    
    success, output = run_cmd("docker ps -a")
    containers = {"running": 0, "stopped": 0, "failed": 0}
    
    if success:
        for line in output.split('\n')[1:]:
            if 'bbh-ai' in line.lower():
                if 'Up' in line:
                    containers["running"] += 1
                    log(f"Running container found", "OK")
                else:
                    containers["stopped"] += 1
                    log(f"Stopped container found", "WARN")
    
    return containers

def check_sandbox_server() -> bool:
    """Check if sandbox server is accessible locally"""
    log("Checking local sandbox server (127.0.0.1:8000)...", "INFO")
    
    success, output = run_cmd('curl -s http://127.0.0.1:8000/health')
    if success and 'healthy' in output:
        log("Local sandbox server is running", "OK")
        return True
    
    log("Local sandbox server not accessible", "WARN")
    return False

def check_python_imports() -> bool:
    """Check if critical Python imports work"""
    log("Checking Python imports...", "INFO")
    
    imports_to_check = [
        ("docker", "docker"),
        ("httpx", "httpx"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("crewai", "crewai"),
    ]
    
    all_ok = True
    for name, module in imports_to_check:
        try:
            __import__(module)
            log(f"  {name}: OK", "OK")
        except ImportError as e:
            log(f"  {name}: MISSING", "ERROR")
            all_ok = False
    
    return all_ok

def check_config() -> bool:
    """Check config.yaml is valid"""
    log("Checking config.yaml...", "INFO")
    
    config_path = Path("config.yaml")
    if not config_path.exists():
        log("config.yaml not found", "ERROR")
        return False
    
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        required = ["llm", "agents", "sandbox", "scan", "reporting"]
        missing = [k for k in required if k not in config]
        
        if missing:
            log(f"config.yaml missing sections: {missing}", "WARN")
        else:
            log("config.yaml is valid", "OK")
            return True
    except Exception as e:
        log(f"config.yaml error: {e}", "ERROR")
    
    return False

def main():
    print("\n" + "="*50)
    print("BBH-AI Sandbox Diagnostics")
    print("="*50 + "\n")
    
    checks = [
        ("Docker Installation", check_docker),
        ("Docker Image", check_image),
        ("Python Imports", check_python_imports),
        ("Configuration File", check_config),
        ("Sandbox Server", check_sandbox_server),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n[*] {name}")
        try:
            results[name] = check_func()
        except Exception as e:
            log(f"Exception: {e}", "ERROR")
            results[name] = False
    
    # Container check (doesn't affect pass/fail)
    print(f"\n[*] Docker Containers")
    containers = check_containers()
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    
    all_passed = all(results.values())
    
    for name, passed in results.items():
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f" {status}: {name}")
    
    print("\n" + "="*50)
    
    if all_passed:
        log("All checks passed!", "OK")
        print("\nYou can run:")
        print("  python main.py --target example.com --yolo")
    else:
        log("Some checks failed. See errors above.", "ERROR")
        print("\nNext steps:")
        print("1. Fix Docker if needed: install Docker Desktop")
        print("2. Rebuild image: python rebuild_docker.py OR rebuild_docker.bat")
        print("3. Install Python packages: pip install -r requirements.txt")
        print("4. Re-run diagnostics: python sandbox_diagnostics.py")
    
    print()
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
