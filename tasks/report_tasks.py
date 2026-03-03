import json
import logging
from pathlib import Path
from celery_app import celery

logger = logging.getLogger(__name__)

@celery.task
def aggregate_report_task(run_id: str, config_dict: dict, target: str):
    """Aggregates all tool findings and generates a final report."""
    run_dir = Path(f"runs/{run_id}")
    all_findings = []

    # Aggregator from local tools/ directory
    for tool_json in run_dir.glob("tools/*/findings.json"):
        try:
            with open(tool_json, 'r') as f:
                findings = json.load(f)
                if isinstance(findings, list):
                    all_findings.extend(findings)
        except Exception as e:
            logger.error(f"Failed to load findings from {tool_json}: {e}")

    # Deduplicate and Validate via original logic
    from validation.validator import Validator
    from telemetry.logger import Telemetry
    from tools.registry import ToolRegistry
    
    telemetry = Telemetry(run_dir / "telemetry.json")
    registry = ToolRegistry(config_dict, run_dir, telemetry)
    validator = Validator(config_dict, run_dir, telemetry)
    
    validated = [validator.validate(f, registry) for f in all_findings]
    final_findings = validator.deduplicate(validated)

    # Generate Report
    from reporting.generator import ReportGenerator
    report_gen = ReportGenerator(config_dict, run_dir, target=target)
    report_paths = report_gen.generate(final_findings)

    return {
        "status": "completed",
        "report_paths": report_paths,
        "total_findings": len(final_findings)
    }
