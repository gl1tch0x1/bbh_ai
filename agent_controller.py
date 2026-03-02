import json
import logging
import re
from crewai import Agent, Task, Crew, Process
from crewai.llm import LLM
from memory.graph import MemoryGraph

# Maps model name prefixes to their provider + config key
_MODEL_PROVIDER_MAP = [
    (('gpt-',),               'openai',    'openai_api_key'),
    (('claude-',),            'anthropic', 'anthropic_api_key'),
    (('gemini-',),            'google',    'google_api_key'),
    (('deepseek-',),          'deepseek',  'deepseek_api_key'),
    (('o1-', 'o3-', 'o4-'),   'openai',    'openai_api_key'),
]


class AgentController:
    def __init__(self, config, workspace, telemetry, tool_registry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.tool_registry = tool_registry
        self.memory_graph = MemoryGraph()
        self.logger = logging.getLogger(__name__)

    def _create_llm(self, agent_config):
        """Resolve LLM provider from model name using a lookup table (not fragile string-in checks)."""
        model = agent_config.get('model', self.config['llm']['default_model'])
        temperature = agent_config.get('temperature', self.config['llm'].get('temperature', 0.2))

        provider = None
        api_key = None
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

    def run(self, attack_surface):
        """Build the multi-agent crew and execute the scan pipeline."""
        agents = []
        tasks = []
        tasks_map = {}  # Explicit task tracking — replaces brittle 'var in locals()' pattern

        agents_cfg = self.config['agents']

        # ── Planner ──────────────────────────────────────────────────────────
        if agents_cfg.get('planner', {}).get('enabled'):
            planner = Agent(
                role='Security Planner',
                goal='Create a prioritized, step-by-step attack plan based on the attack surface',
                backstory=(
                    'You are a senior penetration tester who designs efficient, targeted '
                    'testing strategies based on discovered assets and technology stacks.'
                ),
                tools=self.tool_registry.get_tools('planner'),
                llm=self._create_llm(agents_cfg['planner']),
                verbose=True,
                memory=True,
            )
            agents.append(planner)
            plan_task = Task(
                description=(
                    f"Analyze the following attack surface and create a step-by-step testing plan.\n\n"
                    f"Attack Surface:\n{json.dumps(attack_surface, indent=2)}\n\n"
                    f"Return a JSON array of tasks with keys: tool_name, args, reason."
                ),
                agent=planner,
                expected_output='A JSON array of tasks with tool_name, args, and reason fields.',
            )
            tasks.append(plan_task)
            tasks_map['plan'] = plan_task

        # ── Recon ─────────────────────────────────────────────────────────────
        if agents_cfg.get('recon', {}).get('enabled'):
            recon_agent = Agent(
                role='Reconnaissance Agent',
                goal='Enumerate all endpoints, parameters, and hidden assets',
                backstory=(
                    'You are an expert recon specialist who discovers attack surface '
                    'elements that are not immediately visible.'
                ),
                tools=self.tool_registry.get_tools('recon'),
                llm=self._create_llm(agents_cfg['recon']),
                verbose=True,
                memory=True,
            )
            agents.append(recon_agent)
            recon_task = Task(
                description=(
                    'Execute the recon tasks from the plan. Discover new endpoints, '
                    'parameters, subdomains, and hidden assets. Update and return the '
                    'enriched attack surface as JSON.'
                ),
                agent=recon_agent,
                context=[tasks_map['plan']] if 'plan' in tasks_map else [],
                expected_output='Enriched attack surface JSON with new findings.',
            )
            tasks.append(recon_task)
            tasks_map['recon'] = recon_task

        # ── Exploit ───────────────────────────────────────────────────────────
        if agents_cfg.get('exploit', {}).get('enabled'):
            exploit_agent = Agent(
                role='Vulnerability Testing Agent',
                goal='Test for vulnerabilities using appropriate security tools and validate findings',
                backstory=(
                    'You are a skilled exploit developer who tests for real vulnerabilities '
                    'methodically, avoiding false positives by verifying each finding.'
                ),
                tools=self.tool_registry.get_tools('exploit'),
                llm=self._create_llm(agents_cfg['exploit']),
                verbose=True,
                memory=True,
            )
            agents.append(exploit_agent)
            exploit_task = Task(
                description=(
                    'Run exploitation tasks from the recon results. For each potential '
                    'vulnerability, validate it is exploitable. Return a JSON array of '
                    'findings with keys: title, severity, location, description, payload, poc_lang, poc.'
                ),
                agent=exploit_agent,
                context=[tasks_map['recon']] if 'recon' in tasks_map else (
                    [tasks_map['plan']] if 'plan' in tasks_map else []
                ),
                expected_output=(
                    'JSON array of confirmed vulnerabilities, each with: '
                    'title, severity (critical/high/medium/low/info), location, '
                    'description, payload, poc_lang, poc.'
                ),
            )
            tasks.append(exploit_task)
            tasks_map['exploit'] = exploit_task

        # ── Reporter ──────────────────────────────────────────────────────────
        if agents_cfg.get('reporter', {}).get('enabled'):
            reporter_agent = Agent(
                role='Security Reporter',
                goal='Validate findings, assign CVSS-style severity, and generate PoCs',
                backstory=(
                    'You are a professional bug bounty report writer who produces '
                    'clear, reproducible, and well-structured vulnerability reports.'
                ),
                tools=self.tool_registry.get_tools('reporter'),
                llm=self._create_llm(agents_cfg['reporter']),
                verbose=True,
                memory=True,
            )
            agents.append(reporter_agent)
            last_context_key = next(
                (k for k in ('exploit', 'recon', 'plan') if k in tasks_map), None
            )
            report_task = Task(
                description=(
                    'Review each finding from the exploitation phase. Validate severity, '
                    'remove false positives, and write a PoC for each confirmed finding. '
                    'Return a JSON array with the final validated findings.'
                ),
                agent=reporter_agent,
                context=[tasks_map[last_context_key]] if last_context_key else [],
                expected_output=(
                    'Final JSON array of validated findings, each with: '
                    'title, severity, location, description, payload, poc_lang, poc.'
                ),
            )
            tasks.append(report_task)
            tasks_map['report'] = report_task

        if not agents:
            self.logger.error("No agents enabled in config. Nothing to run.")
            return []

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
            cache=True,  # Optimisation: reuse results for identical tasks
        )

        self.logger.info(f"Starting crew with {len(agents)} agents and {len(tasks)} tasks.")
        result = crew.kickoff()
        findings = self._extract_findings(result, tasks_map)

        # Store findings summary in memory graph
        for i, finding in enumerate(findings):
            self.memory_graph.add_node(f"finding_{i}", finding)

        return findings

    def _extract_findings(self, result, tasks_map):
        """
        Parse the final task output into a list of structured finding dicts.
        Tries JSON parse first; falls back to regex extraction.
        """
        # Prefer the reporter task output; fall back to exploit, then raw result
        raw = None
        for key in ('report', 'exploit', 'recon'):
            if key in tasks_map and hasattr(tasks_map[key], 'output') and tasks_map[key].output:
                raw = str(tasks_map[key].output)
                break

        if raw is None:
            raw = str(result) if result else ''

        if not raw.strip():
            self.logger.warning("CrewAI returned empty output — no findings extracted.")
            return []

        # Strategy 1: Direct JSON parse
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return self._normalise_findings(data)
            elif isinstance(data, dict) and 'findings' in data:
                return self._normalise_findings(data['findings'])
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Extract JSON array buried inside text/markdown
        json_match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return self._normalise_findings(data)
            except (json.JSONDecodeError, ValueError):
                pass

        self.logger.warning(
            "Could not parse findings from CrewAI output as JSON. "
            "Returning raw output as single informational finding."
        )
        return [{
            'title': 'Unparsed Agent Output',
            'severity': 'info',
            'location': 'N/A',
            'description': raw[:2000],
            'payload': '',
            'poc_lang': '',
            'poc': '',
            'validated': False,
        }]

    def _normalise_findings(self, findings):
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