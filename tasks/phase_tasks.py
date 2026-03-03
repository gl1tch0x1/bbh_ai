import logging
from pathlib import Path
from celery_app import celery
from agent_controller import AgentController
from telemetry.logger import Telemetry
from tools.registry import ToolRegistry
from typing import Any, Dict

logger = logging.getLogger(__name__)

def get_agent_controller(run_id: str, config: Dict[str, Any]) -> AgentController:
    workspace = Path(f"runs/{run_id}")
    workspace.mkdir(parents=True, exist_ok=True)
    telemetry = Telemetry(workspace / "telemetry.json")
    registry = ToolRegistry(config, workspace, telemetry)
    return AgentController(config, workspace, telemetry, registry)

@celery.task(bind=True, max_retries=3)
def discovery_phase_task(self, run_id: str, target: str, config: Dict[str, Any]):
    """AI-Orchestrated Discovery Phase (distributed)."""
    try:
        controller = get_agent_controller(run_id, config)
        result = controller.run_phase("discovery", {"target": target})
        return {"status": "completed", "data": result}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)

@celery.task(bind=True, max_retries=3)
def enrichment_phase_task(self, run_id: str, subdomains: list, config: Dict[str, Any]):
    """AI-Orchestrated Enrichment Phase (distributed)."""
    try:
        controller = get_agent_controller(run_id, config)
        result = controller.run_phase("enrichment", {"subdomains": subdomains})
        return {"status": "completed", "data": result}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)

@celery.task(bind=True, max_retries=3)
def web_recon_phase_task(self, run_id: str, live_hosts: list, config: Dict[str, Any]):
    """AI-Orchestrated Web Recon Phase (distributed)."""
    try:
        controller = get_agent_controller(run_id, config)
        result = controller.run_phase("web_recon", {"live_hosts": live_hosts})
        return {"status": "completed", "data": result}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)

@celery.task(bind=True, max_retries=3)
def vuln_scan_phase_task(self, run_id: str, full_context: dict, config: Dict[str, Any]):
    """AI-Orchestrated Vulnerability Scan Phase (distributed)."""
    try:
        controller = get_agent_controller(run_id, config)
        result = controller.run_phase("vuln_scan", full_context)
        return {"status": "completed", "data": result}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=15)
