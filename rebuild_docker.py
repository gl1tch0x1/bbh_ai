#!/usr/bin/env python3
"""
BBH-AI Docker Image Rebuild Script
Builds the unified sandbox Docker image for BBH-AI.
"""

import subprocess
import sys
import os
from pathlib import Path


def main():
    """Build the BBH-AI Docker image."""
    script_dir = Path(__file__).parent
    dockerfile_path = script_dir / "sandbox" / "Dockerfile.sandbox"

    if not dockerfile_path.exists():
        print(f"Error: Dockerfile not found at {dockerfile_path}")
        sys.exit(1)

    image_name = "bbh-ai-unified"

    print(f"Building Docker image '{image_name}' from {dockerfile_path}...")

    try:
        # Run docker build
        cmd = [
            "docker", "build",
            "-f", str(dockerfile_path),
            "-t", image_name,
            "."
        ]

        result = subprocess.run(cmd, cwd=script_dir, check=True, capture_output=True, text=True)
        print("Docker image built successfully!")
        print(f"Image tagged as: {image_name}")

    except subprocess.CalledProcessError as e:
        print(f"Failed to build Docker image: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Docker command not found. Please install Docker.")
        sys.exit(1)


if __name__ == "__main__":
    main()