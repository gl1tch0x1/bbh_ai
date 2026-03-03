import json
import logging
from pathlib import Path
from celery_app import celery
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

def get_run_dir(run_id: str, tool_name: str) -> Path:
    run_dir = Path(f"runs/{run_id}/tools/{tool_name}")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

@celery.task(bind=True, max_retries=3)
def subfinder_task(self, run_id: str, target: str, config_dict: dict):
    """Distributed task for subfinder discovery."""
    run_dir = get_run_dir(run_id, "subfinder")
    output_file = run_dir / "subdomains.json"

    # Idempotency check: Skip if results already exist
    if output_file.exists():
        logger.info(f"Subfinder results for {run_id} already exist. Skipping.")
        with open(output_file, 'r') as f:
            return {"status": "skipped", "count": len(json.load(f))}

    try:
        # We need to re-initialize registry inside the worker context
        # Telemetry is handled per-task to local workspace
        from telemetry.logger import Telemetry
        telemetry = Telemetry(run_dir / "telemetry.json")
        registry = ToolRegistry(config_dict, run_dir, telemetry)
        
        tool = registry.get_tool("subfinder")
        if not tool:
            return {"status": "error", "error": "subfinder tool not found"}

        import asyncio
        result = asyncio.run(tool.run(target=target))
        
        # Save results locally
        with open(output_file, "w") as f:
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
        from telemetry.logger import Telemetry
        telemetry = Telemetry(run_dir / "telemetry.json")
        registry = ToolRegistry(config_dict, run_dir, telemetry)
        
        tool = registry.get_tool("httpx")
        if not tool:
            return {"status": "error", "error": "httpx tool not found"}

        import asyncio
        result = asyncio.run(tool.run(subdomains=subdomains))
        
        with open(output_file, "w") as f:
            json.dump(result, f)

        return {"status": "completed"}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
