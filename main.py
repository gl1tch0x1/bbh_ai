#!/usr/bin/env python3
"""
BB-AI: Multi-Agent AI-Orchestrated Security Testing Engine
Usage: python main.py --target <domain|repo|url|file> [--config config.yaml] [--mode quick] [--ci]
"""

import argparse
import yaml
import sys
import os
import logging
from pathlib import Path
from orchestrator import Orchestrator

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(message)s',
        level=level,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def expand_env_vars(config):
    """Recursively expand environment variables in config dict."""
    if isinstance(config, dict):
        return {k: expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [expand_env_vars(i) for i in config]
    elif isinstance(config, str):
        return os.path.expandvars(config)
    else:
        return config

def load_config(config_path):
    if not Path(config_path).exists():
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    config = expand_env_vars(config)
    return config

def main():
    parser = argparse.ArgumentParser(description="BB-Auto Security Testing Engine")
    parser.add_argument("--target", required=True, help="Target (domain, git repo, URL, or file)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--mode", choices=["quick", "deep", "stealth"], help="Override scan mode")
    parser.add_argument("--ci", action="store_true", help="CI mode (no prompts, exit codes)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    if args.mode:
        config['scan']['mode'] = args.mode
    if args.ci:
        config['ci']['enabled'] = True

    required_sections = ['llm', 'agents', 'sandbox', 'scan', 'reporting']
    for section in required_sections:
        if section not in config:
            logging.error(f"Missing required config section: {section}")
            sys.exit(1)

    orch = Orchestrator(config)
    try:
        result = orch.run(target=args.target)
    except Exception as e:
        logging.exception("Fatal error during scan")
        sys.exit(3)

    if args.ci:
        sys.exit(result.exit_code)
    else:
        print(f"\n[+] Scan completed. Report saved to {result.report_path}")

if __name__ == "__main__":
    main()