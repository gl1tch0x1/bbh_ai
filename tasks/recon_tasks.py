import json
import logging
from pathlib import Path
from celery_app import celery
from tools.registry import ToolRegistry
from tasks.utils import get_run_dir

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3)
def subfinder_task(self, run_id: str, target: str, config_dict: dict):
    """Distributed task for subfinder discovery."""
    run_dir = get_run_dir(run_id, "subfinder")
    output_file = run_dir / "subdomains.json"

    # Idempotency check: skip if results already exist
    if output_file.exists():
        logger.info(f"Subfinder results for {run_id} already exist. Skipping.")
        with open(output_file, 'r', encoding='utf-8') as f:
            return {"status": "skipped", "count": len(json.load(f))}

    try:
        import asyncio
        from telemetry.logger import Telemetry
        telemetry = Telemetry(run_dir / "telemetry.json")
        registry = ToolRegistry(config_dict, run_dir, telemetry)

        tool = registry.get_tool("subfinder")
        if not tool:
            return {"status": "error", "error": "subfinder tool not found"}

        result = asyncio.run(tool.run(target=target))

        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(result, f)

        return {"status": "completed", "count": len(result)}

    except Exception as exc:
        logger.error(f"Subfinder task failed: {exc}")
        raise self.retry(exc=exc, countdown=10)


@celery.task(bind=True, max_retries=3)
def httpx_task(self, run_id: str, subdomains: list, config_dict: dict):
    """Distributed task for HTTP probing."""
    run_dir = get_run_dir(run_id, "httpx")
    output_file = run_dir / "live_hosts.json"

    if output_file.exists():
        return {"status": "skipped"}

    try:
        import asyncio
        from telemetry.logger import Telemetry
        telemetry = Telemetry(run_dir / "telemetry.json")
        registry = ToolRegistry(config_dict, run_dir, telemetry)

        tool = registry.get_tool("httpx")
        if not tool:
            return {"status": "error", "error": "httpx tool not found"}

        result = asyncio.run(tool.run(subdomains=subdomains))

        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(result, f)

        return {"status": "completed"}

    except Exception as exc:
        logger.error(f"HTTPX task failed: {exc}")
        raise self.retry(exc=exc, countdown=10)
