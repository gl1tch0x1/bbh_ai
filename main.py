#!/usr/bin/env python3
"""
BBH-AI: Multi-Agent AI-Orchestrated Security Testing Engine
Usage: python main.py --target <domain|url> [--config config.yaml] [-n] [--ci]
"""

import argparse
import sys
import os
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Callable

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
    """
    Configure logging for the application.
    
    Args:
        level: Logging level to use
        non_interactive: If True, only log WARNING and above to stdout
    """
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
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def expand_env_vars(config: Any) -> Any:
    """
    Recursively expand environment variables in configuration.
    
    Args:
        config: Configuration object (dict, list, str, etc.)
        
    Returns:
        Configuration with all ${VAR} placeholders expanded
    """
    if isinstance(config, dict):
        return {k: expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [expand_env_vars(i) for i in config]
    elif isinstance(config, str):
        try:
            return os.path.expandvars(config)
        except Exception as e:
            logging.warning(f"Failed to expand env vars in '{config}': {e}")
            return config
    return config


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load and parse YAML configuration file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Parsed configuration dictionary
        
    Raises:
        SystemExit: If file not found or parsing fails
    """
    path = Path(config_path)
    if not path.exists():
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        if not isinstance(config, dict):
            logging.error("Config must be a YAML dictionary at root level")
            sys.exit(1)
            
        return expand_env_vars(config)
    except yaml.YAMLError as e:
        logging.error(f"Failed to parse config file: {e}")
        sys.exit(1)
    except IOError as e:
        logging.error(f"Failed to read config file: {e}")
        sys.exit(1)


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate that required configuration sections are present.
    
    Args:
        config: Configuration dictionary to validate
        
    Raises:
        SystemExit: If required sections are missing
    """
    missing = [s for s in REQUIRED_SECTIONS if s not in config]
    if missing:
        logging.error(f"Config is missing required section(s): {', '.join(missing)}")
        sys.exit(1)
    
    config.setdefault('ci', {})
    
    # Validate critical subsections
    try:
        llm_config = config.get('llm', {})
        if not llm_config.get('default_model'):
            logging.warning("No default LLM model specified. Will use first available provider.")
            
        scan_config = config.get('scan', {})
        if scan_config.get('timeout', 0) <= 0:
            logging.warning("Invalid scan timeout. Using default 1800 seconds.")
            scan_config['timeout'] = 1800
    except Exception as e:
        logging.warning(f"Error validating config subsections: {e}")


def print_finding_live(f: Dict[str, Any]) -> None:
    """
    Print a finding to stdout immediately (Strix-style CLI).
    
    Args:
        f: Finding dictionary with severity, title, and location
    """
    icons = {
        "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"
    }
    sev = str(f.get("severity", "info")).lower().strip()
    icon = icons.get(sev, "ℹ️")
    title = f.get("title", "Unknown")
    loc = f.get("location", "N/A")
    
    # Safely truncate long titles
    max_title_len = 100
    if len(title) > max_title_len:
        title = title[:max_title_len-3] + "..."
    
    print(f"{icon}  {sev.upper():<8} {title} @ {loc}")


def main() -> None:
    """
    Main entry point for BBH-AI security testing engine.
    
    Parses CLI arguments, loads configuration, and initiates the scanning workflow.
    """
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
    
    # Setup logging before any other operations
    setup_logging(
        logging.DEBUG if args.verbose else logging.INFO,
        non_interactive=args.non_interactive
    )

    # Load and validate configuration
    try:
        config = load_config(args.config)
        validate_config(config)
    except SystemExit:
        raise
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        logging.debug(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    # Run health checks if requested
    if args.health:
        try:
            from health import HealthChecker
            checker = HealthChecker(config)
            sys.exit(0 if checker.run_all() else 1)
        except Exception as e:
            logging.error(f"Health check failed: {e}")
            sys.exit(1)

    # Validate target is provided
    if not args.target:
        parser.error("--target is required for scanning")

    # Apply CLI overrides to config
    if args.mode:
        config.setdefault('scan', {})['mode'] = args.mode
    if args.ci:
        config.setdefault('ci', {})['enabled'] = True

    # Create orchestrator and run scan
    try:
        orch = Orchestrator(config)
        
        if args.non_interactive:
            print(f"🎯 Target: {args.target}")
            print(f"⚙️  Initializing BBH-AI Subsystems & Sandbox...\n")

        on_finding_cb: Optional[Callable[[Dict[str, Any]], None]] = \
            print_finding_live if args.non_interactive else None
            
        result = asyncio.run(orch.run(target=args.target, on_finding=on_finding_cb))
        
    except KeyboardInterrupt:
        print("\n\n[!] Scan interrupted by user.")
        sys.exit(130)
    except ValueError as e:
        logging.error(f"Invalid input: {e}")
        print(f"\n[!] Error: {e}")
        sys.exit(2)
    except RuntimeError as e:
        logging.error(f"Runtime error during scan: {e}")
        logging.debug(f"Traceback: {traceback.format_exc()}")
        print(f"\n[!] Scan Error: {e}")
        sys.exit(3)
    except Exception as exc:
        logging.exception("Fatal error during scan.")
        print(f"\n[!] Fatal Error: {exc}")
        logging.debug(f"Full traceback: {traceback.format_exc()}")
        sys.exit(3)

    # Report results
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