#!/usr/bin/env python3
"""
BBH-AI: Multi-Agent AI-Orchestrated Security Testing Engine
Usage: python main.py --target <domain|url> [--config config.yaml] [--mode quick|deep|stealth] [--ci] [--verbose]
"""

import argparse
import sys
import os
import logging
from pathlib import Path

import yaml

from orchestrator import Orchestrator

REQUIRED_SECTIONS = ['llm', 'agents', 'sandbox', 'scan', 'reporting']


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s – %(message)s',
        level=level,
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def expand_env_vars(config):
    """Recursively expand ${ENV_VAR} placeholders in config values."""
    if isinstance(config, dict):
        return {k: expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [expand_env_vars(i) for i in config]
    elif isinstance(config, str):
        return os.path.expandvars(config)
    return config


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        logging.error(f"Failed to parse config YAML: {exc}")
        sys.exit(1)
    if not isinstance(config, dict):
        logging.error("Config file is empty or not a valid YAML mapping.")
        sys.exit(1)
    return expand_env_vars(config)


def validate_config(config: dict) -> None:
    """Validate required top-level sections are present."""
    missing = [s for s in REQUIRED_SECTIONS if s not in config]
    if missing:
        logging.error(f"Config is missing required section(s): {', '.join(missing)}")
        sys.exit(1)

    # Ensure 'ci' section exists so orchestrator can safely access it
    config.setdefault('ci', {})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BBH-AI – Multi-Agent AI Security Testing Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target",  required=True,  help="Target domain, URL, or Git repo")
    parser.add_argument("--config",  default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--mode",    choices=["quick", "deep", "stealth"], help="Override scan mode")
    parser.add_argument("--ci",      action="store_true", help="CI mode: no prompts, exit codes")
    parser.add_argument("--verbose", action="store_true", help="Enable debug-level logging")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    validate_config(config)

    # Apply CLI overrides
    if args.mode:
        config['scan']['mode'] = args.mode
    if args.ci:
        config['ci']['enabled'] = True
        config['ci']['exit_codes'] = True

    orch = Orchestrator(config)
    try:
        result = orch.run(target=args.target)
    except KeyboardInterrupt:
        logging.warning("Scan interrupted by user.")
        sys.exit(130)
    except Exception:
        logging.exception("Fatal error during scan.")
        sys.exit(3)

    print(f"\n[+] Scan complete. Report: {result.report_path}")

    if args.ci:
        sys.exit(result.exit_code)


if __name__ == "__main__":
    main()