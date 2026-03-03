from typing import Any, Dict, List, Tuple, Optional

# Maps model name prefixes to their provider + config key
_MODEL_PROVIDER_MAP: List[Tuple[Tuple[str, ...], str, str]] = [
    (('gpt-',),               'openai',    'openai_api_key'),
    (('claude-',),            'anthropic', 'anthropic_api_key'),
    (('gemini-',),            'google',    'google_api_key'),
    (('deepseek-',),          'deepseek',  'deepseek_api_key'),
    (('o1-', 'o3-', 'o4-'),   'openai',    'openai_api_key'),
]


class AgentController:
    def __init__(self, config: Dict[str, Any], workspace: Any, telemetry: Any, tool_registry: Any):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.tool_registry = tool_registry
        self.memory_graph = MemoryGraph()
        self.logger = logging.getLogger(__name__)

    def _create_llm(self, agent_config: Dict[str, Any]) -> LLM:
        """Resolve LLM provider from model name using a lookup table."""
        model = agent_config.get('model', self.config['llm']['default_model'])
        temperature = agent_config.get('temperature', self.config['llm'].get('temperature', 0.2))

        provider: Optional[str] = None
        api_key: Optional[str] = None
        for prefixes, prov, key_name in _MODEL_PROVIDER_MAP:
            if any(model.startswith(p) for p in prefixes):
                provider = prov
                api_key = self.config['llm'].get(key_name)
                break

        if provider is None:
            self.logger.warning(f"Unknown model '{model}', defaulting to openai provider.")
            provider = 'openai'
            api_key = self.config['llm'].get('openai_api_key')

        if not api_key:
            self.logger.error(f"No API key configured for provider '{provider}' (model: {model})")
            raise ValueError(f"Missing API key for provider '{provider}'")

        return LLM(
            provider=provider,
            model=model,
            api_key=api_key,
            temperature=temperature,
        )

    def run(self, attack_surface: Any) -> Dict[str, Any]:
        """Legacy compatibility method for single-run scans."""
        return self.run_phase("full", attack_surface)

    def run_phase(self, phase_name: str, context: Dict[str, Any]) -> Any:
        """Execute a specific phase of the scanning workflow."""
        self.logger.info(f"AgentController starting phase: {phase_name}")
        
        agents: List[Agent] = []
        tasks: List[Task] = []
        
        if phase_name == "discovery":
            agents, tasks = self._build_discovery_phase(context)
        elif phase_name == "enrichment":
            agents, tasks = self._build_enrichment_phase(context)
        elif phase_name == "web_recon":
            agents, tasks = self._build_web_recon_phase(context)
        elif phase_name == "vuln_scan":
            agents, tasks = self._build_vuln_scan_phase(context)
        else:
            self.logger.error(f"Unknown phase: {phase_name}")
            return {}

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
            cache=True,
        )

        result = crew.kickoff()
        return self._parse_phase_result(result, phase_name)

    def _build_discovery_phase(self, context: Dict[str, Any]) -> Tuple[List[Agent], List[Task]]:
        planner = Agent(
            role='Discovery Specialist',
            goal='Identify all basic attack surface assets including domains, subdomains, and related IPs.',
            backstory='Expert OSINT investigator with deep knowledge in DNS enumeration, WHOIS analysis, and public repository metadata extraction. Your goal is to map the broadest possible attack surface.',
            tools=self.tool_registry.get_tools('discovery'),
            llm=self._create_llm(self.config['agents']['planner']),
        )
        task = Task(
            description=f"Perform deep discovery for target: {context.get('target')}. Use subfinder, whois, and OSINT tools to find all related subdomains and IP addresses.",
            agent=planner,
            expected_output="A structured list of subdomains and IP addresses found during discovery."
        )
        return [planner], [task]

    def _build_enrichment_phase(self, context: Dict[str, Any]) -> Tuple[List[Agent], List[Task]]:
        recon = Agent(
            role='Enrichment Specialist',
            goal='Validate subdomains and enrich them with network metadata (DNS, SSL, Open Ports).',
            backstory='Technical infrastructure auditor. You specialize in verifying asset liveness using dnsx and puredns, and profiling services via nmap and tlsx.',
            tools=self.tool_registry.get_tools('hosts'),
            llm=self._create_llm(self.config['agents']['recon']),
        )
        task = Task(
            description=f"Validate these subdomains and identify live hosts: {context.get('subdomains')}. For each live host, perform port scanning and service profiling.",
            agent=recon,
            expected_output="A detailed list of live hosts with associated ports, services, and SSL/TLS metadata."
        )
        return [recon], [task]

    def _build_web_recon_phase(self, context: Dict[str, Any]) -> Tuple[List[Agent], List[Task]]:
        web_specialist = Agent(
            role='Web Recon Analyst',
            goal='Profile web technologies, crawl endpoints, and identify hidden attack surface in web apps.',
            backstory='Expert in modern web architecture. You excel at fingerprinting tech stacks with CMSeeK and wafw00f, and discovering hidden endpoints via crawling and JS analysis.',
            tools=self.tool_registry.get_tools('web'),
            llm=self._create_llm(self.config['agents']['recon']),
        )
        task = Task(
            description=f"Analyze tech stacks and endpoints for live hosts: {context.get('live_hosts')}. Focus on identifying APIs, JS secrets, and hidden web directories.",
            agent=web_specialist,
            expected_output="A mapping of URLs to discovered technologies, endpoints, and parsed JavaScript findings."
        )
        return [web_specialist], [task]

    def _build_vuln_scan_phase(self, context: Dict[str, Any]) -> Tuple[List[Agent], List[Task]]:
        hacker = Agent(
            role='Vulnerability Researcher',
            goal='Identify and validate high-impact vulnerabilities with reproducible PoCs.',
            backstory='Senior penetration tester specializing in non-intrusive exploit validation. You prioritize finding SQLi, XSS, RCE, and SSRF. You use OOB (Out-of-Band) interactions for maximum blind discovery.',
            tools=self.tool_registry.get_tools('vuln'),
            llm=self._create_llm(self.config['agents']['exploit']),
        )
        task = Task(
            description=f"Conduct targeted vulnerability scanning on the attack surface. Use the following context gathered in previous phases: {json.dumps(context)}. Prioritize OOB testing if SSRF or RCE are suspected.",
            agent=hacker,
            expected_output="A JSON-formatted array of findings, each including title, severity, location, description, and a reproducible PoC."
        )
        return [hacker], [task]

    def _parse_phase_result(self, result: Any, phase_name: str) -> Any:
        """Standardize the crew output back into a dictionary."""
        raw = str(result)
        
        if phase_name == "vuln_scan":
            # For vulnerability scanning, we need structured findings
            return {"findings": self._extract_findings(result)}

        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"results": data}
        except:
            return {"raw_output": raw}

    def _extract_findings(self, result: Any) -> List[Dict[str, Any]]:
        """
        Parse the final task output into a list of structured finding dicts.
        Tries JSON parse first; falls back to regex extraction.
        """
        raw = str(result) if result else ''
        if not raw.strip():
            self.logger.warning("CrewAI returned empty output — no findings extracted.")
            return []

        # Strategy 1: Direct JSON parse
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return self._normalise_findings(data)
            elif isinstance(data, dict):
                if 'findings' in data and isinstance(data['findings'], list):
                    return self._normalise_findings(data['findings'])
                return self._normalise_findings([data])
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Extract JSON array buried inside text/markdown
        json_match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    return self._normalise_findings(data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 3: Single finding dict match
        dict_match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if dict_match:
            try:
                data = json.loads(dict_match.group())
                return self._normalise_findings([data])
            except (json.JSONDecodeError, ValueError):
                pass

        self.logger.warning("Could not parse findings as JSON. Returning raw as info.")
        return [{
            'title': 'Unparsed Agent Output',
            'severity': 'info',
            'location': 'N/A',
            'description': raw[:2000],
            'validated': False,
        }]

    def _normalise_findings(self, findings: List[Any]) -> List[Dict[str, Any]]:
        """Ensure every finding dict has all required keys with safe defaults."""
        required_keys = {
            'title': 'Unknown Finding',
            'severity': 'info',
            'location': '',
            'description': '',
            'payload': '',
            'poc_lang': '',
            'poc': '',
            'validated': False,
        }
        normalised = []
        for f in findings:
            if isinstance(f, dict):
                entry = {k: f.get(k, default) for k, default in required_keys.items()}
                normalised.append(entry)
        return normalised
