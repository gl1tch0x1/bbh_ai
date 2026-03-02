import os
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from agent_controller import AgentController
from telemetry.logger import Telemetry
from reporting.generator import ReportGenerator
from tools.registry import ToolRegistry
from validation.validator import Validator
import subprocess


@dataclass
class ScanResult:
    """Structured result object returned from Orchestrator.run()."""
    report_path: str
    exit_code: int


class Orchestrator:
    def __init__(self, config):
        self.config = config
        self.run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        self.workspace = Path(config['reporting']['output_dir']) / self.run_id
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.telemetry = Telemetry(self.workspace / "telemetry.json")
        self.tool_registry = ToolRegistry(config, self.workspace, self.telemetry)
        self.agent_controller = AgentController(config, self.workspace, self.telemetry, self.tool_registry)
        self.validator = Validator(config, self.workspace, self.telemetry)
        self.logger = logging.getLogger(__name__)
        self._rate_limit = config.get('scan', {}).get('rate_limit', 0)  # requests/sec
        self._js_limit = config.get('scan', {}).get('js_file_limit', 10)

    def _validate_env(self):
        self.logger.info("Validating environment...")
        if self.config['sandbox']['enabled']:
            try:
                subprocess.run(["docker", "info"], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                self.logger.error("Docker is not running or not installed.")
                raise RuntimeError("Docker required but not available.")
            except FileNotFoundError:
                self.logger.error("Docker executable not found.")
                raise RuntimeError("Docker not installed or not on PATH.")
        for key in ['openai_api_key', 'anthropic_api_key', 'google_api_key', 'deepseek_api_key']:
            if not self.config['llm'].get(key):
                self.logger.warning(f"LLM key {key} is missing. Some agents may not work.")
        self.logger.info("Environment validation passed.")

    def _rate_sleep(self):
        """Respect configured rate limit between tool invocations."""
        if self._rate_limit and self._rate_limit > 0:
            time.sleep(1.0 / self._rate_limit)

    def _prepare_target(self, target):
        self.logger.info(f"Preparing target: {target}")
        attack_surface = {
            "target": target,
            "type": "domain",
            "subdomains": [],
            "live_hosts": [],
            "urls": [],
            "tech_stack": {},
            "js_files": [],
            "endpoints": []
        }

        # Subdomain enumeration
        subfinder = self.tool_registry.get_tool("subfinder")
        if subfinder:
            result = subfinder.run(domain=target)
            attack_surface["subdomains"] = result.get("subdomains", [])
            self._rate_sleep()
        else:
            self.logger.warning("Subfinder tool not available")

        # Live host probing
        httpx = self.tool_registry.get_tool("httpx")
        live_hosts = []
        if httpx and attack_surface["subdomains"]:
            sub_file = self.workspace / "subs_for_httpx.txt"
            sub_file.write_text("\n".join(attack_surface["subdomains"]))
            result = httpx.run(host_list=str(sub_file))
            live_hosts = result.get("results", [])
            attack_surface["live_hosts"] = live_hosts
            for item in live_hosts:
                url = item.get("url")
                tech = item.get("tech", [])
                if url:
                    attack_surface["tech_stack"][url] = tech
            self._rate_sleep()

        # URL collection
        gau = self.tool_registry.get_tool("gau")
        if gau:
            result = gau.run(domain=target)
            attack_surface["urls"] = result.get("urls", [])
            self._rate_sleep()

        # JS file discovery and parsing
        js_urls = [u for u in attack_surface["urls"] if u.endswith('.js')]
        js_parser = self.tool_registry.get_tool("js_parser")
        if js_parser and js_urls:
            for js in js_urls[:self._js_limit]:
                result = js_parser.run(js_url=js, base_url=target)
                if "endpoints" in result:
                    attack_surface["endpoints"].extend(result["endpoints"])
                self._rate_sleep()
            attack_surface["js_files"] = js_urls

        # Technology detection for main domain and live hosts
        tech_detect = self.tool_registry.get_tool("tech_detect")
        if tech_detect:
            for host in live_hosts:
                url = host.get("url")
                if url and url not in attack_surface["tech_stack"]:
                    result = tech_detect.run(url=url)
                    attack_surface["tech_stack"][url] = result.get("technologies", [])
                    self._rate_sleep()
            main_url = f"https://{target}"
            if main_url not in attack_surface["tech_stack"]:
                result = tech_detect.run(url=main_url)
                attack_surface["tech_stack"][main_url] = result.get("technologies", [])
                self._rate_sleep()

        self.logger.info(
            f"Attack surface prepared: {len(attack_surface['subdomains'])} subdomains, "
            f"{len(attack_surface['live_hosts'])} live hosts, "
            f"{len(attack_surface['urls'])} URLs, "
            f"{len(attack_surface['endpoints'])} endpoints from JS."
        )
        return attack_surface

    def _calculate_exit_code(self, findings):
        severities = {f.get('severity', '').lower() for f in findings}
        if 'critical' in severities:
            return 1
        elif 'high' in severities:
            return 2
        return 0

    def run(self, target):
        self._validate_env()
        try:
            attack_surface = self._prepare_target(target)
            raw_findings = self.agent_controller.run(attack_surface)

            # Validate and deduplicate findings
            validated = [self.validator.validate(f, self.tool_registry) for f in raw_findings]
            findings = self.validator.deduplicate(validated)

            report_gen = ReportGenerator(self.config, self.workspace, target=target)
            report_paths = report_gen.generate(findings)

            # Use markdown path as primary display path; fall back to first available
            primary_report = (
                report_paths.get("markdown")
                or report_paths.get("json")
                or report_paths.get("csv")
                or str(self.workspace)
            )

            exit_code = (
                self._calculate_exit_code(findings)
                if self.config.get('ci', {}).get('exit_codes')
                else 0
            )
            return ScanResult(report_path=primary_report, exit_code=exit_code)
        finally:
            # Always persist telemetry, even on failure
            try:
                self.telemetry.save()
            except Exception:
                self.logger.warning("Failed to save telemetry data.")