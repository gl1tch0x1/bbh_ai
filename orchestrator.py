import copy
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, List
import asyncio
import traceback

from agent_controller import AgentController
from celery_app import celery
from ci.notifier import CINotifier
from engine.auto_healer import AutoHealer
from engine.storage import AtomicFileStore
from engine.tci import TCICalculator
from memory.graph import MemoryGraph
from reporting.generator import ReportGenerator
from sandbox.client import SandboxClient
from telemetry.logger import Telemetry
from tools.registry import ToolRegistry


class Orchestrator:
    """
    Core engine managing the phased scanning workflow and multi-agent system.
    Integrates TCI scoring, memory graph context, sandbox isolation, and CI/CD reporting.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        self.workspace = Path(f"runs/{run_id}")
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self._setup_logger()

        # Core Components
        self.store = AtomicFileStore(str(self.workspace))
        self.telemetry = Telemetry(self.workspace / "telemetry.json")
        self.sandbox = SandboxClient(config, base_workspace=self.workspace)

        # Inject sandbox into config so ToolRegistry+Analyzer can use it
        self.config['_sandbox_client'] = self.sandbox

        self.tool_registry = ToolRegistry(config, self.workspace, self.telemetry)
        self.agent_controller = AgentController(
            config, self.workspace, self.telemetry, self.tool_registry
        )
        self.memory_graph = MemoryGraph(self.workspace / "memory_graph.json")

        self.auto_healer = AutoHealer(config, self.agent_controller)
        self.tci_calculator = TCICalculator()

        self.state: Dict[str, Any] = {
            "run_id": run_id,
            "target": None,
            "start_time": time.time(),
            "status": "initialized",
            "phases_completed": [],
            "tci": {"score": 0, "band": "UNKNOWN"},
        }
        self.logger.info(f"Orchestrator initialized. Run ID: {run_id}")

    def _setup_logger(self) -> None:
        log_file = self.workspace / "orchestrator.log"
        fh = logging.FileHandler(log_file)
        fh.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
        )
        self.logger.addHandler(fh)

    # ── Main Execution ────────────────────────────────────────────────────────
    async def run(
        self,
        target: str,
        on_finding: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Any:
        """
        Execute the full autonomous scan workflow.
        Includes TCI scoring, validation, and PoC generation.
        
        Args:
            target: The target domain or URL to scan
            on_finding: Callback function to handle findings in real-time
            
        Returns:
            Scan result object containing report paths and exit code
            
        Raises:
            ValueError: If target is invalid
            RuntimeError: If scan fails to complete
        """
        if not target or not isinstance(target, str):
            raise ValueError("Target must be a non-empty string")
            
        self.state["target"] = target
        self.state["status"] = "running"
        self.store.save("state", self.state)
        self.logger.info(f"Starting autonomous scan against target: {target}")

        try:
            scan_mode = self.config.get('scan', {}).get('mode', 'quick')
            if scan_mode == 'distributed':
                return await self._run_distributed(target)
            return await self._run_local(target, on_finding=on_finding)
        except Exception as e:
            self.logger.error(f"Scan failed with error: {str(e)}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            self.state["status"] = "failed"
            self.store.save("state", self.state)
            raise RuntimeError(f"Scan failed: {str(e)}") from e

    async def _run_local(
        self,
        target: str,
        on_finding: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Any:
        """
        Execute the local scan workflow through all phases.
        
        Args:
            target: The target domain or URL to scan
            on_finding: Callback function to handle findings in real-time
            
        Returns:
            MockResult object containing report paths and exit code
        """
        start_phase = self.config.get('scan', {}).get('start_phase', 'A')
        phases = [
            ('A', "discovery",  self._phase_a_discovery),
            ('B', "enrichment", self._phase_b_enrichment),
            ('C', "web_recon",  self._phase_c_webrecon),
            ('D', "vuln_scan",  self._phase_d_vulnscan),
            ('E', "validation", self._phase_e_validation),
            ('F', "reporting",  self._phase_f_reporting),
        ]

        # Skip phases before start_phase
        execute_phases = [p for p in phases if p[0] >= start_phase]
        
        try:
            for name, key, func in execute_phases:
                self.logger.info(f"=== Starting Phase {name}: {key.upper()} ===")
                try:
                    # Wrap sync phase functions in to_thread since Orchestrator is now async
                    await asyncio.to_thread(func, self.state)

                    if on_finding and key in ("vuln_scan", "validation"):
                        latest: List[Dict[str, Any]] = self.state.get("findings", [])
                        for f in latest:
                            on_finding(f)

                    self.state["phases_completed"].append(name)
                    self.store.save("state", self.state)

                except Exception as exc:
                    self.logger.error(
                        f"Phase {name} failed: {exc}. Attempting Auto-Heal."
                    )
                    self.logger.debug(f"Traceback: {traceback.format_exc()}")
                    healed = await self.auto_healer.heal(exc, self.state)
                    if not healed:
                        self.logger.error(f"Auto-Heal failed for Phase {name}.")
                        self.state["status"] = "failed"
                        self.store.save("state", self.state)
                        # Continue with remaining phases unless critical failure
                        continue
                        
        finally:
            # Ensure cleanup happens even if phases fail
            try:
                await self.sandbox.close()
                self.telemetry.save()
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
                
        self.logger.info("Scan completed natively.")

        class MockResult:
            def __init__(self, rp, ec):
                self.report_path = rp
                self.exit_code = ec

        report_paths = self.state.get("report_paths", {})
        exit_code = self.state.get("exit_code", 0)
        return MockResult(report_paths, exit_code)

    # ── Phase Implementations ─────────────────────────────────────────────────
    def _phase_a_discovery(self, context: Dict[str, Any]) -> None:
        """
        Execute Phase A: Asset Discovery.
        
        Args:
            context: The scan context dictionary to update with findings
        """
        try:
            if "discovery" not in self.config.get("scan", {}).get("phases", []):
                self.logger.info("Phase A (Discovery) disabled in config.")
                return

            # 1. External OSINT Tools
            subfinder = self.tool_registry.get_tool("subfinder")
            subs: List[str] = []
            if subfinder:
                try:
                    import asyncio
                    subs_result = asyncio.run(subfinder.run(target=context["target"]))
                    if isinstance(subs_result, dict) and "subdomains" in subs_result:
                        subs = subs_result["subdomains"]
                    elif isinstance(subs_result, list):
                        subs = subs_result
                    self.logger.info(f"Subfinder found {len(subs)} subdomains")
                except Exception as e:
                    self.logger.warning(f"Subfinder failed: {e}")
                    subs = []

            # 2. Agent Discovery
            agent_ctx = {
                "target": context["target"],
                "tool_subdomains": subs,
                "tci_score": context.get("tci", {}).get("score", 0),
            }
            
            try:
                res = self.agent_controller.run_phase("discovery", agent_ctx)
            except Exception as e:
                self.logger.error(f"Agent discovery failed: {e}")
                res = {}

            merged_subs = list(set(subs + res.get("subdomains", [])))
            context["subdomains"] = merged_subs
            context["ips"] = res.get("ips", [])

            # Calculate initial TCI based on discovered breadth
            if merged_subs:
                try:
                    tci = self.tci_calculator.analyze(context["target"], endpoints=merged_subs)
                    context["tci"] = tci
                    self.logger.info(
                        f"[TCI] Scored {tci['score']}/100 ({tci['band']}) after Phase A"
                    )
                except Exception as e:
                    self.logger.warning(f"TCI calculation failed: {e}")
                    
        except Exception as e:
            self.logger.error(f"Phase A failed with unexpected error: {e}")
            raise

    def _phase_b_enrichment(self, context: Dict[str, Any]) -> None:
        """
        Execute Phase B: Host Enrichment.
        
        Args:
            context: The scan context dictionary to update with findings
        """
        try:
            agent_ctx = {
                "subdomains": context.get("subdomains", []),
                "tci_score":  context.get("tci", {}).get("score", 0),
                "tci_band":   context.get("tci", {}).get("band", "UNKNOWN"),
            }
            
            try:
                res = self.agent_controller.run_phase("enrichment", agent_ctx)
            except Exception as e:
                self.logger.error(f"Agent enrichment failed: {e}")
                res = {}
                
            context["live_hosts"] = res.get("live_hosts", [])
            context["port_data"] = res.get("port_data", {})

            # Re-calc TCI with live hosts
            if context["live_hosts"]:
                try:
                    tci = self.tci_calculator.analyze(
                        context["target"],
                        live_hosts=context["live_hosts"],
                        endpoints=context.get("subdomains", []),
                    )
                    context["tci"] = tci
                except Exception as e:
                    self.logger.warning(f"TCI calculation failed: {e}")
        except Exception as e:
            self.logger.error(f"Phase B failed with unexpected error: {e}")
            raise

    def _phase_c_webrecon(self, context: Dict[str, Any]) -> None:
        agent_ctx = {
            "live_hosts": context.get("live_hosts", []),
            "tci_score":  context.get("tci", {}).get("score", 0),
            "tci_band":   context.get("tci", {}).get("band", "UNKNOWN"),
        }
        res = self.agent_controller.run_phase("web_recon", agent_ctx)
        context["tech_stack"]  = res.get("tech_stack", [])
        context["endpoints"]   = res.get("endpoints", [])
        context["js_findings"] = res.get("js_findings", [])

        # Final TCI calc with full surface data
        tci = self.tci_calculator.analyze(
            context["target"],
            live_hosts=context.get("live_hosts", []),
            tech_stack=context["tech_stack"],
            endpoints=context["endpoints"],
            js_findings=context["js_findings"],
        )
        context["tci"] = tci
        self.logger.info(
            f"[TCI Final] Scored {tci['score']}/100 ({tci['band']}) — "
            f"Strategy: {tci['scan_depth']}"
        )

    def _phase_d_vulnscan(self, context: Dict[str, Any]) -> None:
        # Pass the full context plus TCI data securely to agents
        agent_ctx = copy.deepcopy(context)
        agent_ctx["tci_score"] = context.get("tci", {}).get("score", 0)
        agent_ctx["tci_band"]  = context.get("tci", {}).get("band", "UNKNOWN")

        res = self.agent_controller.run_phase("vuln_scan", agent_ctx)
        findings = res.get("findings", [])

        if self.config.get("scan", {}).get("diff_mode", False):
            findings = self._apply_diff_mode(findings)

        context["findings"] = findings

    def _phase_e_validation(self, context: Dict[str, Any]) -> None:
        """New Validation Phase — dedicated agent confirms findings + CVSS + PoC."""
        findings = context.get("findings", [])
        if not findings:
            return

        agent_ctx = {
            "target":    context["target"],
            "findings":  findings,
            "tci_score": context.get("tci", {}).get("score", 0),
        }
        res = self.agent_controller.run_phase("validation", agent_ctx)
        validated_findings = res.get("findings", [])

        # Merge results, keeping only confirmed ones
        final_findings = [
            f for f in validated_findings
            if str(f.get('confirmed', 'true')).lower() == 'true'
            or str(f.get('validated', 'true')).lower() == 'true'
        ]
        context["findings"] = final_findings
        self.logger.info(
            f"Phase E (Validation) completed. "
            f"{len(final_findings)}/{len(findings)} confirmed."
        )

    def _phase_f_reporting(self, context: Dict[str, Any]) -> None:
        """Reporter Agent writes the final report, then CI/CD dispatch."""
        findings = context.get("findings", [])

        # 1. Let Reporter Agent enrich the findings one last time
        if findings:
            res = self.agent_controller.run_phase(
                "reporting", {"target": context["target"], "findings": findings}
            )
            findings = res.get("findings", findings)
            context["findings"] = findings

        # 2. Extract exit code based on severity
        # 0 = clean/low/med, 1 = critical, 2 = high
        exit_code = 0
        counts = {"critical": 0, "high": 0}
        for f in findings:
            sev = str(f.get('severity', '')).lower()
            if sev == 'critical':
                counts['critical'] += 1
                exit_code = 1
            elif sev == 'high':
                counts['high'] += 1
                if exit_code == 0:
                    exit_code = 2

        context["exit_code"] = exit_code

        # 3. Generate Reports (Markdown/JSON/CSV)
        generator = ReportGenerator(self.config, self.workspace, context["target"])
        report_paths = generator.generate(findings, tci=context.get("tci"))
        context["report_paths"] = report_paths

        # 4. CI/CD Notifications
        if self.config.get("ci", {}).get("enabled"):
            notifier = CINotifier(self.config)
            primary_report = str(
                report_paths.get('markdown') or list(report_paths.values())[0]
            )
            notifier.notify(
                target=context["target"],
                findings=findings,
                report_path=primary_report,
                exit_code=exit_code,
            )

        self.logger.info(
            f"Reporting Complete. Exit Code: {exit_code}. Paths: {report_paths}"
        )

    # ── Diff Mode Helper ──────────────────────────────────────────────────────
    def _apply_diff_mode(self, current_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from validation.validator import Validator
        validator = Validator(self.config, self.workspace, self.telemetry)
        previous = self.store.load("baseline_findings")
        if not previous:
            self.store.save("baseline_findings", current_findings)
            for f in current_findings:
                f["is_new"] = True
            return current_findings

        fp_current = [self._fingerprint(f) for f in current_findings]
        fp_previous = {self._fingerprint(f) for f in previous}

        final = []
        for i, f in enumerate(current_findings):
            if fp_current[i] not in fp_previous:
                f["is_new"] = True
                final.append(f)
            else:
                f["is_new"] = False
                final.append(f)

        self.store.save("baseline_findings", current_findings)
        return final

    @staticmethod
    def _fingerprint(f: Dict[str, Any]) -> str:
        import hashlib
        data = f"{f.get('title')}|{f.get('location')}|{f.get('payload')}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    # ── Distributed Execution (Celery) ────────────────────────────────────────
    async def _run_distributed(self, target: str) -> Any:
        self.logger.info("Initializing Distributed Scan via Celery.")
        # Need absolute import to avoid circular dependency
        from tasks.phase_tasks import (
            discovery_phase_task,
            enrichment_phase_task,
            web_recon_phase_task,
            vuln_scan_phase_task,
        )
        from tasks.report_tasks import aggregate_report_task

        # Phase A
        task_a = discovery_phase_task.apply_async(
            args=[self.state["run_id"], target, self.config]
        )
        res_a = task_a.get()
        data_a = res_a.get("data", {})
        subdomains = data_a.get("subdomains", [])
        self.logger.info(f"Phase A completed remotely: {len(subdomains)} subdomains")

        # Phase B
        task_b = enrichment_phase_task.apply_async(
            args=[self.state["run_id"], subdomains, self.config]
        )
        res_b = task_b.get()
        live_hosts = res_b.get("data", {}).get("live_hosts", [])
        self.logger.info(f"Phase B completed remotely: {len(live_hosts)} hosts")

        # Phase C
        task_c = web_recon_phase_task.apply_async(
            args=[self.state["run_id"], live_hosts, self.config]
        )
        task_c.get()

        # Phase D
        task_d = vuln_scan_phase_task.apply_async(
            args=[
                self.state["run_id"],
                {"target": target, "live_hosts": live_hosts, "subdomains": subdomains},
                self.config,
            ]
        )
        task_d.get()

        # Phase E + F (Aggregated in report task for distributed)
        task_rep = aggregate_report_task.apply_async(
            args=[self.state["run_id"], self.config, target]
        )
        final = task_rep.get()
        self.logger.info(f"Distributed Scan Complete. Report: {final}")

        class MockResult:
            def __init__(self, rp, ec):
                self.report_path = rp
                self.exit_code = ec

        return MockResult(final.get("report_paths"), 0)
