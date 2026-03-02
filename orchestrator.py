import os
import time
import logging
from pathlib import Path
from agent_controller import AgentController
from telemetry.logger import Telemetry
from reporting.generator import ReportGenerator
from tools.registry import ToolRegistry
import subprocess

class Orchestrator:
    def __init__(self, config):
        self.config = config
        self.run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        self.workspace = Path(config['reporting']['output_dir']) / self.run_id
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.telemetry = Telemetry(self.workspace / "telemetry.json")
        self.tool_registry = ToolRegistry(config, self.workspace, self.telemetry)
        self.agent_controller = AgentController(config, self.workspace, self.telemetry, self.tool_registry)
        self.logger = logging.getLogger(__name__)

    def _validate_env(self):
        self.logger.info("Validating environment...")
        if self.config['sandbox']['enabled']:
            try:
                subprocess.run(["docker", "info"], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                self.logger.error("Docker is not running or not installed.")
                raise RuntimeError("Docker required but not available.")
        for key in ['openai_api_key', 'anthropic_api_key', 'google_api_key', 'deepseek_api_key']:
            if not self.config['llm'].get(key):
                self.logger.warning(f"LLM key {key} is missing. Some agents may not work.")
        self.logger.info("Environment validation passed.")

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
        else:
            self.logger.warning("Subfinder tool not available")

        # Live host probing
        httpx = self.tool_registry.get_tool("httpx")
        live_hosts = []
        if httpx and attack_surface["subdomains"]:
            sub_file = self.workspace / "subs_for_httpx.txt"
            sub_file.write_text("\n".join(attack_surface["subdomains"]))
            result = httpx.run(list=str(sub_file))
            live_hosts = result.get("results", [])
            attack_surface["live_hosts"] = live_hosts
            for item in live_hosts:
                url = item.get("url")
                tech = item.get("tech", [])
                if url:
                    attack_surface["tech_stack"][url] = tech

        # URL collection
        gau = self.tool_registry.get_tool("gau")
        if gau:
            result = gau.run(domain=target)
            attack_surface["urls"] = result.get("urls", [])

        # JS file discovery and parsing
        js_urls = [u for u in attack_surface["urls"] if u.endswith('.js')]
        js_parser = self.tool_registry.get_tool("js_parser")
        if js_parser and js_urls:
            for js in js_urls[:10]:
                result = js_parser.run(js_url=js, base_url=target)
                if "endpoints" in result:
                    attack_surface["endpoints"].extend(result["endpoints"])
            attack_surface["js_files"] = js_urls

        # Technology detection for main domain and live hosts
        tech_detect = self.tool_registry.get_tool("tech_detect")
        if tech_detect:
            for host in live_hosts:
                url = host.get("url")
                if url and url not in attack_surface["tech_stack"]:
                    result = tech_detect.run(url=url)
                    attack_surface["tech_stack"][url] = result.get("technologies", [])
            main_url = f"https://{target}"
            if main_url not in attack_surface["tech_stack"]:
                result = tech_detect.run(url=main_url)
                attack_surface["tech_stack"][main_url] = result.get("technologies", [])

        self.logger.info(f"Attack surface prepared: {len(attack_surface['subdomains'])} subdomains, {len(attack_surface['live_hosts'])} live hosts, {len(attack_surface['urls'])} URLs, {len(attack_surface['endpoints'])} endpoints from JS.")
        return attack_surface

    def _calculate_exit_code(self, findings):
        critical = any(f.get('severity') == 'critical' for f in findings)
        high = any(f.get('severity') == 'high' for f in findings)
        if critical:
            return 1
        elif high:
            return 2
        else:
            return 0

    def run(self, target):
        self._validate_env()
        attack_surface = self._prepare_target(target)
        findings = self.agent_controller.run(attack_surface)
        report_gen = ReportGenerator(self.config, self.workspace)
        report_path = report_gen.generate(findings)
        exit_code = self._calculate_exit_code(findings) if self.config.get('ci', {}).get('exit_codes') else 0
        return type('Result', (), {'report_path': report_path, 'exit_code': exit_code})