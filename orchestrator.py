import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple, TYPE_CHECKING
from dataclasses import dataclass
import json

# Celery for distributed scanning
try:
    from celery import group, chain
    from tasks.recon_tasks import subfinder_task, httpx_task
    from tasks.vuln_tasks import nuclei_task
    from tasks.report_tasks import aggregate_report_task
    from tasks.phase_tasks import discovery_phase_task, enrichment_phase_task, web_recon_phase_task, vuln_scan_phase_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

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
        
        # Sandbox Client (Industrial Execution Bridge)
        from sandbox.client import SandboxClient
        try:
            # pass the orchestrator workspace so the container can mount it
            self.sandbox = SandboxClient(config, base_workspace=self.workspace)
            if self.sandbox.enabled:
                self.logger.info("✓ Sandbox initialized successfully")
            else:
                self.logger.warning("⚠ Sandbox disabled - using local tool execution")
        except Exception as e:
            self.logger.warning(f"⚠ Sandbox initialization failed: {e}")
            self.logger.info("  Continuing with local tool execution")
            # Create a disabled sandbox client
            self.sandbox = type('DisabledSandbox', (), {
                'enabled': False,
                'execute': lambda *args, **kw: None
            })()
        
        # Inject sandbox into config so registry can share it with tool instances
        self.config['_sandbox_client'] = self.sandbox

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
        
        # Industrial Storage Layer
        from engine.storage import AtomicFileStore
        self.storage = AtomicFileStore(self.workspace)
        
        # AI Self-Healing
        from engine.auto_healer import AutoHealer
        self.auto_healer = AutoHealer(config, self.agent_controller)

        # Hybrid Vulnerability Analyzer
        from engine.analyzer import VulnerabilityAnalyzer
        # provide sandbox client so analyzer can execute validation payloads
        self.vuln_analyzer = VulnerabilityAnalyzer(config, self.agent_controller, self.tool_registry, self.sandbox)

        # CI Integration
        from ci.notifier import CINotifier
        self.ci_notifier = CINotifier(config)

        # Resource Management: Semaphore to limit concurrent tool executions
        max_concurrent = config.get('scan', {}).get('max_concurrent_tools', 5)
        self._tool_semaphore = asyncio.Semaphore(max_concurrent)

    async def _execute_with_semaphore(self, phase_name: str, task_coro) -> Any:
        """Execute a task with semaphore control to limit concurrency."""
        async with self._tool_semaphore:
            self.logger.debug(f"[{phase_name}] Acquiring execution slot (available: {self._tool_semaphore._value})")
            return await task_coro
    
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
        except (ValueError, IndexError):
            self.logger.warning(f"Invalid start_phase '{start_phase}', starting from A")
            start_idx = 0
            
        current_phases = phases[start_idx:]
        final_findings = []

        try:
            if self.config.get('scan', {}).get('mode') == 'distributed' and CELERY_AVAILABLE:
                self.logger.info("[ORCHESTRATOR] Distributed mode enabled")
                return await self.run_distributed(target)

            # Phase A: Discovery
            if "A" in current_phases:
                try:
                    self.logger.debug("[Phase A] Starting discovery phase")
                    state["phase_data"]["A"] = await self._execute_with_semaphore(
                        "Phase A", self._run_phase_a(target)
                    )
                except Exception as e:
                    self.logger.error(f"[Phase A] Error: {e}")
                    if not await self.auto_healer.heal(e, {"phase": "A", "target": target}):
                        self.logger.info("[Phase A] Continuing despite error (recovery failed)")
                    else:
                        state["phase_data"]["A"] = await self._execute_with_semaphore(
                            "Phase A (Recovery)", self._run_phase_a(target)
                        )

            # Phase B: Host enrichment
            if "B" in current_phases:
                try:
                    self.logger.debug("[Phase B] Starting enrichment phase")
                    state["phase_data"]["B"] = await self._execute_with_semaphore(
                        "Phase B", self._run_phase_b(state)
                    )
                except Exception as e:
                    self.logger.error(f"[Phase B] Error: {e}")
                    if not await self.auto_healer.heal(e, {"phase": "B", "state": state}):
                        self.logger.info("[Phase B] Continuing despite error (recovery failed)")
                    else:
                        state["phase_data"]["B"] = await self._execute_with_semaphore(
                            "Phase B (Recovery)", self._run_phase_b(state)
                        )

            # Phase C: Web recon
            if "C" in current_phases:
                try:
                    self.logger.debug("[Phase C] Starting web recon phase")
                    state["phase_data"]["C"] = await self._execute_with_semaphore(
                        "Phase C", self._run_phase_c(state)
                    )
                except Exception as e:
                    self.logger.error(f"[Phase C] Error: {e}")
                    if not await self.auto_healer.heal(e, {"phase": "C", "state": state}):
                        self.logger.info("[Phase C] Continuing despite error (recovery failed)")
                    else:
                        state["phase_data"]["C"] = await self._execute_with_semaphore(
                            "Phase C (Recovery)", self._run_phase_c(state)
                        )

            # Phase D: Vulnerability scan
            if "D" in current_phases:
                try:
                    self.logger.debug("[Phase D] Starting vulnerability scan phase")
                    state["phase_data"]["D"] = await self._execute_with_semaphore(
                        "Phase D", self._run_phase_d(state)
                    )
                except Exception as e:
                    self.logger.error(f"[Phase D] Error: {e}")
                    if not await self.auto_healer.heal(e, {"phase": "D", "state": state}):
                        self.logger.info("[Phase D] Continuing despite error (recovery failed)")
                    else:
                        state["phase_data"]["D"] = await self._execute_with_semaphore(
                            "Phase D (Recovery)", self._run_phase_d(state)
                        )

            # Phase E: Correlation & Reporting
            try:
                self.logger.debug("[Phase E] Starting correlation and reporting phase")
                final_findings = await self._run_phase_e(state)
            except Exception as e:
                self.logger.error(f"[Phase E] Error during correlation: {e}")
                final_findings = list(state.get("phase_data", {}).get("D", {}).get("findings", []))
            
            # Generate Reports
            try:
                from reporting.generator import ReportGenerator
                report_gen = ReportGenerator(self.config, self.workspace, target=target)
                report_paths = report_gen.generate(final_findings)
            except Exception as e:
                self.logger.error(f"Failed to generate reports: {e}")
                report_paths = {}

            primary_report = report_paths.get('markdown', str(self.workspace))
            
            # CI Logic
            exit_code = 0
            try:
                if self.config.get('ci', {}).get('enabled'):
                    exit_code = self._calculate_exit_code(final_findings)
                    await self._notify_ci(target, final_findings, primary_report, exit_code)
            except Exception as e:
                self.logger.error(f"CI notification failed: {e}")

            return ScanResult(
                findings=final_findings,
                report_path=report_paths,
                exit_code=exit_code
            )

        except Exception as e:
            self.logger.exception(f"Orchestrator fatal error: {e}")
            # Return partial results with error indication
            return ScanResult(
                findings=final_findings,
                report_path={},
                exit_code=1
            )
        finally:
            try:
                self.telemetry.save()
            except Exception as e:
                self.logger.error(f"Failed to save telemetry: {e}")
            # cleanup sandbox resources if any
            try:
                if hasattr(self.sandbox, 'close'):
                    await self.sandbox.close()
            except Exception as cleanup_e:
                self.logger.warning(f"Error closing sandbox: {cleanup_e}")
            duration = time.time() - start_time
            self.logger.info(f"🏁 [ORCHESTRATOR] Scan complete. Duration: {duration:.2f}s")

    async def run_distributed(self, target: str) -> ScanResult:
        """Execute the full phased workflow via Celery workers."""
        self.logger.info(f"🌐 [ORCHESTRATOR] Starting DISTRIBUTED Scan for: {target}")
        
        # 1. Define the High-IQ Distributed Chain
        # This mirrors the A-E phased workflow using Celery tasks
        workflow = chain(
            discovery_phase_task.si(self.run_id, target, self.config),
            enrichment_phase_task.si(self.run_id, [], self.config), 
            web_recon_phase_task.si(self.run_id, [], self.config),
            vuln_scan_phase_task.si(self.run_id, {"target": target}, self.config),
            aggregate_report_task.si(self.run_id, self.config, target)
        )
        
        job = workflow.apply_async()
        self.logger.info(f"🌐 [ORCHESTRATOR] Distributed Workflow Dispatched. Job ID: {job.id}")
        
        # Wait for completion (poll)
        final_result = await self._wait_for_job(job)
        
        findings = final_result.get('total_findings', [])
        exit_code = 0
        if self.config.get('ci', {}).get('enabled'):
            exit_code = self._calculate_exit_code(findings)
        return ScanResult(
            findings=findings,
            report_path=final_result.get('report_paths', {}),
            exit_code=exit_code
        )

    async def _wait_for_job(self, job):
        """Poll celery for job completion."""
        while not job.ready():
            await asyncio.sleep(2)
        return job.get()

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
        
        # Optional AI-driven interpretation/validation step via VulnerabilityAnalyzer
        findings_to_process = raw_findings
        if self.vuln_analyzer and self.config.get('scan', {}).get('use_vuln_analyzer', True):
            self.logger.info("[Phase E] Running vulnerability analyzer on raw findings")
            analyzed = []
            coros = []
            for f in raw_findings:
                tool_name = f.get('tool', 'unknown')
                coros.append(self.vuln_analyzer.analyze_finding(tool_name, f.get('outputs', f), state.get('target')))
            results = await asyncio.gather(*coros, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    self.logger.warning(f"Analyzer raised exception: {r}")
                elif r is None:
                    # skip false positives or failed interpretation
                    continue
                else:
                    analyzed.append(r)
            findings_to_process = analyzed
            self.logger.info(f"[Phase E] Analyzer produced {len(analyzed)} interpreted findings")

        # Validation & Deduplication
        validated = [self.validator.validate(f, self.tool_registry) for f in findings_to_process]
        unique_findings = self.validator.deduplicate(validated)

        # Diff Mode: Highlight new findings vs previous run
        if self.config.get('scan', {}).get('diff_mode', True):
            unique_findings = self._apply_diff_mode(state.get("target"), unique_findings)

        return unique_findings

    def _apply_diff_mode(self, target: str, current_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify which findings are new compared to the most recent previous scan."""
        previous_scans = sorted(Path(self.config.get('reporting', {}).get('output_dir', './scans')).glob("run_*"), reverse=True)
        # Skip current workspace
        previous_scans = [p for p in previous_scans if p != self.workspace]

        previous_findings_fps = set()
        for scan_dir in previous_scans:
            report_json = scan_dir / "report.json"
            if report_json.exists():
                try:
                    with open(report_json, 'r') as f:
                        data = json.load(f)
                        if data.get("target") == target:
                            for fnd in data.get("findings", []):
                                fingerprint = f"{fnd.get('title')}|{fnd.get('location')}|{fnd.get('payload')}"
                                previous_findings_fps.add(fingerprint)
                            break # Found most recent scan for this target
                except: continue

        for fnd in current_findings:
            fp = f"{fnd.get('title')}|{fnd.get('location')}|{fnd.get('payload')}"
            fnd["is_new"] = fp not in previous_findings_fps
            if fnd["is_new"]:
                self.logger.info(f"✨ New vulnerability discovered: {fnd.get('title')}")

        return current_findings

    def _calculate_exit_code(self, findings: List[Dict[str, Any]]) -> int:
        """Determines exit code: 1 if critical/high vulnerabilities exist."""
        severities = {str(f.get('severity', '')).lower() for f in findings}
        if any(s in ('critical', 'high') for s in severities):
            return 1
        return 0

    async def _notify_ci(self, target: str, findings: List[Dict[str, Any]], primary_report: str, exit_code: int) -> None:
        """Send asynchronous notifications for CI pipelines."""
        try:
            # Using to_thread for the potentially blocking notification logic
            await asyncio.to_thread(
                self.ci_notifier.notify, target, findings, primary_report, exit_code
            )
        except Exception as e:
            self.logger.error(f"❌ [ORCHESTRATOR] Notification failure: {e}")
            if self.config.get('scan', {}).get('ai_swarm'):
                self.logger.info("🧠 [Swarm Recovery] Attempting notification fallback via secondary channels...")
                # Placeholder for future swarm notification redundancy
