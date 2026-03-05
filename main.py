#!/usr/bin/env python3
"""
BBH-AI: Multi-Agent AI-Orchestrated Security Testing Engine
Usage: python main.py --target <domain|url> [--config config.yaml] [-n] [--ci]
"""

import argparse
import sys
import os
import logging
from pathlib import Path
from typing import Any, Dict

import yaml
import asyncio

# ── Load .env FIRST, before any other imports that might read env vars ────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass

from orchestrator import Orchestrator

REQUIRED_SECTIONS = ['llm', 'agents', 'sandbox', 'scan', 'reporting']


def setup_logging(level: int = logging.INFO, non_interactive: bool = False) -> None:
    if non_interactive:
        # In non-interactive mode, only log WARNING+ to stdout to keep it clean for findings
        logging.basicConfig(level=logging.WARNING, format='%(message)s')
    else:
        logging.basicConfig(
            format='%(asctime)s [%(levelname)s] %(name)s – %(message)s',
            level=level,
            datefmt='%Y-%m-%d %H:%M:%S',
        )

# Mute noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("docker").setLevel(logging.WARNING)


def expand_env_vars(config: Any) -> Any:
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
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return expand_env_vars(config)


def validate_config(config: dict) -> None:
    missing = [s for s in REQUIRED_SECTIONS if s not in config]
    if missing:
        logging.error(f"Config is missing required section(s): {', '.join(missing)}")
        sys.exit(1)
    config.setdefault('ci', {})


def print_finding_live(f: Dict[str, Any]) -> None:
    """Print a finding to stdout immediately (Strix-style CLI)."""
    icons = {
        "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"
    }
    sev = str(f.get("severity", "info")).lower()
    icon = icons.get(sev, "ℹ️")
    title = f.get("title", "Unknown")
    loc = f.get("location", "N/A")
    print(f"{icon}  {sev.upper():<8} {title} @ {loc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BBH-AI – Multi-Agent AI Security Testing Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target",  required=False, help="Target domain or URL")
    parser.add_argument("--config",  default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--mode",    choices=["quick", "standard", "deep", "stealth"], help="Override scan mode")
    parser.add_argument("-n", "--non-interactive", action="store_true", help="Strix-style clean output with live findings")
    parser.add_argument("--ci",      action="store_true", help="CI mode: force exit codes and webhooks")
    parser.add_argument("--verbose", action="store_true", help="Enable debug-level logging")
    parser.add_argument("--health",  action="store_true", help="Run system health diagnostic")
    args = parser.parse_args()

    setup_logging(
        logging.DEBUG if args.verbose else logging.INFO,
        non_interactive=args.non_interactive
    )

    config = load_config(args.config)
    validate_config(config)

    if args.health:
        from health import HealthChecker
        checker = HealthChecker(config)
        sys.exit(0 if checker.run_all() else 1)

    if not args.target:
        parser.error("--target is required")

    if args.mode:
        config['scan']['mode'] = args.mode
    if args.ci:
        config['ci']['enabled'] = True

    orch = Orchestrator(config)
    
    if args.non_interactive:
        print(f"🎯 Target: {args.target}")
        print(f"⚙️  Initializing BBH-AI Subsystems & Sandbox...\n")

    try:
        on_finding_cb = print_finding_live if args.non_interactive else None
        result = asyncio.run(orch.run(target=args.target, on_finding=on_finding_cb))
    except KeyboardInterrupt:
        print("\n\n[!] Scan interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        logging.exception("Fatal error during scan.")
        print(f"\n[!] Fatal Error: {exc}")
        sys.exit(3)

    print(f"\n📊 Scan complete.")
    if isinstance(result.report_path, dict):
        for fmt, path in result.report_path.items():
            print(f"   {fmt.upper()}: {path}")
    else:
        print(f"   Report: {result.report_path}")

    # Standardized exit codes: 0 = clean/low/medium, 1 = critical, 2 = high
    exit_code = getattr(result, 'exit_code', 0)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()