#!/usr/bin/env python3
"""
BBH-AI Docker Image Rebuild Script with Network Diagnostics
Builds the unified sandbox Docker image for BBH-AI with robust error handling.
"""

import subprocess
import sys
import os
import time
import socket
from pathlib import Path

# Configuration flag to skip network diagnostics for offline environments
# Set to True if you're in an air-gapped environment or have connectivity issues
# You can also set this via environment variable: export SKIP_BBH_NETWORK_DIAGNOSTICS=true
SKIP_NETWORK_DIAGNOSTICS = os.environ.get('SKIP_BBH_NETWORK_DIAGNOSTICS', 'false').lower() == 'true'


def diagnose_network():
    """Run network diagnostics before attempting build."""
    print("\n📡 Running Network Diagnostics...")
    
    # Test DNS resolution
    print("  Testing DNS resolution (registry-1.docker.io)...")
    try:
        result = socket.gethostbyname('registry-1.docker.io')
        print(f"    ✓ DNS resolved: {result}")
    except socket.gaierror as e:
        print(f"    ✗ DNS resolution failed: {e}")
        return False
    
    # Test basic connectivity
    print("  Testing Docker Hub connectivity (port 443)...")
    try:
        sock = socket.create_connection(("registry-1.docker.io", 443), timeout=5)
        sock.close()
        print(f"    ✓ Can reach registry-1.docker.io:443")
    except (socket.timeout, socket.error) as e:
        print(f"    ✗ Cannot reach Docker Hub: {e}")
        print("\n🔧 Troubleshooting:")
        print("    1. Check your internet connection: ping 8.8.8.8")
        print("    2. Check DNS: nslookup registry-1.docker.io")
        print("    3. Check Docker daemon: docker info")
        print("    4. Try: sudo systemctl restart docker")
        return False
    
    return True


def diagnose_docker():
    """Check Docker daemon health."""
    print("\n🐳 Checking Docker Daemon...")
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("    ✓ Docker daemon is running")
            return True
        else:
            print(f"    ✗ Docker daemon error: {result.stderr}")
            return False
    except FileNotFoundError:
        print("    ✗ Docker command not found")
        return False
    except subprocess.TimeoutExpired:
        print("    ✗ Docker daemon timeout")
        return False


def test_docker_hub():
    """Test if we can pull a small image from Docker Hub."""
    print("\n🧪 Testing Docker Hub Access...")
    try:
        result = subprocess.run(
            ["docker", "pull", "alpine:latest"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print("    ✓ Successfully pulled alpine:latest from Docker Hub")
            return True
        else:
            print(f"    ✗ Failed to pull from Docker Hub")
            if "timeout" in result.stderr.lower():
                print("    Reason: Network timeout")
            elif "connection refused" in result.stderr.lower():
                print("    Reason: Connection refused (firewall?)")
            else:
                print(f"    Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("    ✗ Pull operation timed out (network issue)")
        return False
    except Exception as e:
        print(f"    ✗ Unexpected error: {e}")
        return False


def build_docker_image_with_retry(dockerfile_path: Path, image_name: str, max_retries: int = 3):
    """Build Docker image with retry logic and exponential backoff."""
    print(f"\n🏗️  Building Docker image '{image_name}' from {dockerfile_path}...")
    
    # Get the project root directory (parent of sandbox directory)
    project_root = dockerfile_path.parent.parent
    
    for attempt in range(1, max_retries + 1):
        print(f"\n📦 Build attempt {attempt}/{max_retries}...")
        
        try:
            cmd = [
                "docker", "build",
                "-f", str(dockerfile_path),
                "-t", image_name,
                "--progress=plain",  # Better output for diagnostics
                "."
            ]
            
            result = subprocess.run(
                cmd,
                cwd=project_root,  # Run from project root to ensure correct context
                capture_output=False,  # Show live output for debugging
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                print(f"\n✅ Docker image built successfully!")
                print(f"   Image tagged as: {image_name}")
                return True
            else:
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    print(f"\n⚠️  Build failed, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"\n❌ Build failed after {max_retries} attempts")
                    print("\n🔧 Troubleshooting tips:")
                    print("   1. Check network connectivity: ping 8.8.8.8")
                    print("   2. Check DNS resolution: nslookup registry-1.docker.io")
                    print("   3. Try building with network diagnostics disabled:")
                    print("      Edit rebuild_docker.py and set SKIP_NETWORK_DIAGNOSTICS = True")
                    print("   4. Pre-download base images on a machine with better connectivity:")
                    print("      docker pull python:3.11-slim")
                    print("   5. Use a Docker registry mirror if behind a firewall")
                    return False
                    
        except subprocess.TimeoutExpired:
            print(f"\n⏱️  Build timeout (1 hour limit exceeded)")
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                return False
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            return False
    
    return False


def main():
    """Main build orchestration."""
    script_dir = Path(__file__).parent
    dockerfile_path = script_dir / "sandbox" / "Dockerfile.sandbox"

    if not dockerfile_path.exists():
        print(f"❌ Error: Dockerfile not found at {dockerfile_path}")
        sys.exit(1)

    image_name = "bbh-ai-unified"

    print("=" * 60)
    print("  BBH-AI Docker Image Builder v2.0")
    print("=" * 60)

    # Run diagnostics (unless skipped)
    if not SKIP_NETWORK_DIAGNOSTICS:
        if not diagnose_docker():
            print("\n❌ Docker daemon is not available")
            sys.exit(1)

        if not diagnose_network():
            print("\n⚠️  Network connectivity issues detected")
            print("\nOptions:")
            print("  1. Fix your network and retry")
            print("  2. Use a local Docker mirror (configure docker daemon)")
            print("  3. Try building on a different network")
            response = input("\nContinue anyway? (y/N): ").strip().lower()
            if response != 'y':
                sys.exit(1)

        if not test_docker_hub():
            print("\n⚠️  Docker Hub is not accessible")
            print("\nOptions:")
            print("  1. Fix network connectivity")
            print("  2. Configure Docker to use a local mirror")
            print("  3. Pre-pull the base image on a machine with internet")
            response = input("\nContinue anyway? (y/N): ").strip().lower()
            if response != 'y':
                sys.exit(1)
    else:
        print("\n⏭️  Skipping network diagnostics (SKIP_NETWORK_DIAGNOSTICS=True)")

    # Attempt build with retry logic
    success = build_docker_image_with_retry(dockerfile_path, image_name, max_retries=3)

    if success:
        print("\n" + "=" * 60)
        print("  ✅ Build Successful!")
        print("=" * 60)
        print(f"\nYou can now run the sandbox:")
        print(f"  docker run -it {image_name} bash")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("  ❌ Build Failed")
        print("=" * 60)
        print("\nTroubleshooting:")
        print("  1. Check network: ping 8.8.8.8")
        print("  2. Check DNS: nslookup registry-1.docker.io")
        print("  3. Restart Docker: sudo systemctl restart docker")
        print("  4. View daemon logs: journalctl -u docker")
        print("\nFor persistent network issues:")
        print("  - Configure Docker to use an HTTP proxy")
        print("  - Use a local Docker registry mirror")
        print("  - Build on a machine with better network connectivity")
        sys.exit(1)


if __name__ == "__main__":
    main()