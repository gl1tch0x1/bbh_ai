import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from telemetry.logger import Telemetry
    from tools.registry import ToolRegistry
    from agent_controller import AgentController
    from validation.validator import Validator
    from reporting.generator import ReportGenerator

@dataclass
class ScanResult:
    """Structured result returned from Orchestrator.run()."""
    report_path: Union[str, Dict[str, str]]
    exit_code: int
    findings: List[Dict[str, Any]]

class Orchestrator:
    """
    The central brain of BBH-AI. Orchestrates the A-E phased workflow.
    Refactored for asyncio to support high-performance scanning and resource management.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        
        # Determine workspace
        out_dir = config.get('reporting', {}).get('output_dir', './scans')
        self.workspace = Path(out_dir) / self.run_id
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        
        # Telemetry & Tool Registry
        from telemetry.logger import Telemetry
        self.telemetry = Telemetry(self.workspace / "telemetry.json")
        
        from tools.registry import ToolRegistry
        self.tool_registry = ToolRegistry(config, self.workspace, self.telemetry)
        
        # AI Controller
        from agent_controller import AgentController
        self.agent_controller = AgentController(config, self.workspace, self.telemetry, self.tool_registry)
        
        # Utilities
        from validation.validator import Validator
        self.validator = Validator(config, self.workspace, self.telemetry)
        
        # CI Integration
        from ci.notifier import CINotifier
        self.ci_notifier = CINotifier(config)

        # Resource Management: Semaphore to limit concurrent tool executions
        max_concurrent = config.get('scan', {}).get('max_concurrent_tools', 5)
        self._tool_semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, target: str) -> ScanResult:
        """Execute the full phased workflow asynchronously."""
        self.logger.info(f"🚀 [ORCHESTRATOR] Starting Phased Scan for: {target}")
        start_time = time.time()
        
        # Initialize state with target and workflow control
        state: Dict[str, Any] = {
            "target": target, 
            "start_time": start_time,
            "phase_data": {}
        }
        
        phases = ["A", "B", "C", "D", "E"]
        start_phase = self.config.get('scan', {}).get('start_phase', 'A')
        
        try:
            start_idx = phases.index(start_phase)
        except ValueError:
            start_idx = 0
        
        current_phases = phases[start_idx:]

        try:
            # Phase A: Discovery
            if "A" in current_phases:
                state["phase_data"]["A"] = await self._run_phase_a(target)
            else:
                state["phase_data"]["A"] = {}

            # Phase B: Host enrichment
            if "B" in current_phases:
                state["phase_data"]["B"] = await self._run_phase_b(state)
            else:
                state["phase_data"]["B"] = {}

            # Phase C: Web recon
            if "C" in current_phases:
                state["phase_data"]["C"] = await self._run_phase_c(state)
            else:
                state["phase_data"]["C"] = {}

            # Phase D: Vulnerability scan
            if "D" in current_phases:
                state["phase_data"]["D"] = await self._run_phase_d(state)
            else:
                state["phase_data"]["D"] = {"findings": []}

            # Phase E: Correlation & Reporting
            final_findings = await self._run_phase_e(state)
            
            # Generate Reports
            from reporting.generator import ReportGenerator
            report_gen = ReportGenerator(self.config, self.workspace, target=target)
            report_paths = report_gen.generate(final_findings)

            primary_report = report_paths.get('markdown', str(self.workspace))
            
            # CI Logic
            exit_code = 0
            if self.config.get('ci', {}).get('enabled'):
                exit_code = self._calculate_exit_code(final_findings)
                await self._notify_ci(target, final_findings, primary_report, exit_code)

            return ScanResult(
                findings=final_findings,
                report_path=report_paths,
                exit_code=exit_code
            )

        finally:
            self.telemetry.save()
            duration = time.time() - start_time
            self.logger.info(f"🏁 [ORCHESTRATOR] Scan complete. Duration: {duration:.2f}s")

    async def _run_phase_a(self, target: str) -> Dict[str, Any]:
        self.logger.info("--- [Phase A: Discovery (OSINT & Subdomains)] ---")
        return await asyncio.to_thread(
            self.agent_controller.run_phase, "discovery", {"target": target}
        )

    async def _run_phase_b(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("--- [Phase B: Host Enrichment (IP/DNS/Ports)] ---")
        subdomains = state["phase_data"].get("A", {}).get("subdomains", [])
        return await asyncio.to_thread(
            self.agent_controller.run_phase, "enrichment", {"subdomains": subdomains}
        )

    async def _run_phase_c(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("--- [Phase C: Web Recon (Tech Stack & Endpoints)] ---")
        live_hosts = state["phase_data"].get("B", {}).get("live_hosts", [])
        return await asyncio.to_thread(
            self.agent_controller.run_phase, "web_recon", {"live_hosts": live_hosts}
        )

    async def _run_phase_d(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("--- [Phase D: Vulnerability Scanning (OOB Focused)] ---")
        # Ensure Phase D has the full context
        return await asyncio.to_thread(
            self.agent_controller.run_phase, "vuln_scan", state
        )

    async def _run_phase_e(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.logger.info("--- [Phase E: Final Correlation & Deduplication] ---")
        raw_findings = state["phase_data"].get("D", {}).get("findings", [])
        
        # Validation & Deduplication
        validated = [self.validator.validate(f, self.tool_registry) for f in raw_findings]
        return self.validator.deduplicate(validated)

    def _calculate_exit_code(self, findings: List[Dict[str, Any]]) -> int:
        """Determines exit code: 1 if critical/high vulnerabilities exist."""
        severities = {str(f.get('severity', '')).lower() for f in findings}
        if any(s in ('critical', 'high') for s in severities):
            return 1
        return 0

    async def _notify_ci(self, target: str, findings: List[Dict[str, Any]], primary_report: str, exit_code: int) -> None:
        """Send asynchronous notifications for CI pipelines."""
        # Using to_thread for the potentially blocking notification logic
        await asyncio.to_thread(
            self.ci_notifier.notify, target, findings, primary_report, exit_code
        )
