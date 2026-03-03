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
import asyncio

# ── Load .env FIRST, before any other imports that might read env vars ───────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path, override=False)
        # override=False: real shell env vars always take precedence over .env
except ImportError:
    pass  # python-dotenv not installed — fall back to OS env vars only

from orchestrator import Orchestrator

REQUIRED_SECTIONS = ['llm', 'agents', 'sandbox', 'scan', 'reporting']


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s – %(message)s',
        level=level,
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def expand_env_vars(config: any) -> any:
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
    """Validate required top-level sections and default optional ones."""
    missing = [s for s in REQUIRED_SECTIONS if s not in config]
    if missing:
        logging.error(f"Config is missing required section(s): {', '.join(missing)}")
        sys.exit(1)
    # Ensure ci section exists so orchestrator can safely access it
    config.setdefault('ci', {})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BBH-AI – Multi-Agent AI Security Testing Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --target example.com --mode deep\n"
            "  python main.py --target example.com --mode quick --ci --verbose\n"
            "  python main.py --health\n"
        ),
    )
    parser.add_argument("--target",  required=False, help="Target domain or URL (required unless --update or --health is used)")
    parser.add_argument("--config",  default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--mode",    choices=["quick", "deep", "stealth"], help="Override scan mode")
    parser.add_argument("--phase",   choices=["A", "B", "C", "D", "E"], help="Run scan starting from a specific phase")
    parser.add_argument("--oob",     action="store_true", help="Explicitly enable Out-of-Band (interactsh) testing")
    parser.add_argument("--ci",      action="store_true", help="CI mode: no prompts, structured exit codes")
    parser.add_argument("--verbose", action="store_true", help="Enable debug-level logging")
    parser.add_argument("--health",  action="store_true", help="Run system health diagnostic and tools verification")
    parser.add_argument("--update", "-u", action="store_true", help="Check for and install updates from GitHub")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    validate_config(config)

    # ── Handle Update ────────────────────────────────────────────────────────
    if args.update:
        from update_manager import UpdateManager
        manager = UpdateManager(root_dir=str(Path(__file__).parent))
        if manager.update():
            print("[+] Update successful. Please restart bbh-ai.")
            sys.exit(0)
        else:
            print("[-] Update failed. Check logs for details.")
            sys.exit(1)

    # ── Handle Health Check ──────────────────────────────────────────────────
    if args.health:
        from health import HealthChecker
        checker = HealthChecker(config)
        success = checker.run_all()
        sys.exit(0 if success else 1)

    # --target is required if NOT updating or checking health
    if not args.target:
        parser.error("--target is required unless --update or --health is used.")

    # Apply CLI overrides
    if args.mode:
        config['scan']['mode'] = args.mode
    if args.ci:
        config['ci']['enabled'] = True
        config['ci']['exit_codes'] = True
    
    # New flags for phased workflow and OOB
    if args.phase:
        config['scan']['start_phase'] = args.phase
    if args.oob:
        # Ensure vuln section exists
        config.setdefault('tools', {}).setdefault('vuln', {}).setdefault('interactsh', {})
        config['tools']['vuln']['interactsh']['enabled'] = True

    orch = Orchestrator(config)
    try:
        # 🔗 High-Performance Async Execution
        result = asyncio.run(orch.run(target=args.target))
    except KeyboardInterrupt:
        logging.warning("Scan interrupted by user (Ctrl+C).")
        sys.exit(130)
    except Exception:
        logging.exception("Fatal error during scan.")
        sys.exit(3)

    print(f"\n[+] Scan complete.")
    if isinstance(result.report_path, dict):
        for fmt, path in result.report_path.items():
            print(f"    {fmt.upper()}: {path}")
    else:
        print(f"    Report: {result.report_path}")

    if args.ci:
        sys.exit(result.exit_code)


if __name__ == "__main__":
    main()