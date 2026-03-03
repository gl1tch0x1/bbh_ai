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
def nuclei_task(self, run_id: str, targets: list, config_dict: dict):
    """Distributed task for nuclei vulnerability scanning."""
    run_dir = get_run_dir(run_id, "nuclei")
    output_file = run_dir / "findings.json"

    if output_file.exists():
        return {"status": "skipped"}

    try:
        from telemetry.logger import Telemetry
        telemetry = Telemetry(run_dir / "telemetry.json")
        registry = ToolRegistry(config_dict, run_dir, telemetry)
        
        tool = registry.get_tool("nuclei")
        if not tool:
            return {"status": "error", "error": "nuclei tool not found"}

        import asyncio
        # Nuclei handles lists of targets
        result = asyncio.run(tool.run(targets=targets))
        
        with open(output_file, "w") as f:
            json.dump(result, f)

        return {"status": "completed", "findings_count": len(result)}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=15)
