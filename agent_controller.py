import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, TYPE_CHECKING

# Use forward references for crewai types to keep static analysis happy
if TYPE_CHECKING:
    from crewai import Agent, Task, Crew, Process

# CrewAI & LangChain Imports — track availability for early failure
_CREWAI_AVAILABLE = False
try:
    from crewai import Agent, Task, Crew, Process
    _CREWAI_AVAILABLE = True
except ImportError:
    Agent = Task = Crew = Process = None  # type: ignore

try:
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatOpenAI = ChatAnthropic = ChatGoogleGenerativeAI = None  # type: ignore

import time
from memory.graph import MemoryGraph

# Maps model name prefixes to their provider + config key
_MODEL_PROVIDER_MAP: List[Tuple[Tuple[str, ...], str, str]] = [
    (('gpt-',),             'openai',    'openai_api_key'),
    (('claude-',),          'anthropic', 'anthropic_api_key'),
    (('gemini-',),          'google',    'google_api_key'),
    (('deepseek-',),        'deepseek',  'openai_api_key'),
    (('o1-', 'o3-', 'o4-'), 'openai',   'openai_api_key'),
]


class AgentController:
    def __init__(
        self,
        config: Dict[str, Any],
        workspace: Any,
        telemetry: Any,
        tool_registry: Any,
    ):
        if not _CREWAI_AVAILABLE:
            raise RuntimeError(
                "crewai library is required by AgentController but is not installed."
            )

        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.tool_registry = tool_registry

        graph_path = Path(workspace) / "memory_graph.json" if workspace else None
        self.memory_graph = MemoryGraph(graph_path)
        self.logger = logging.getLogger(__name__)

    # ── LLM Factory ───────────────────────────────────────────────────────────
    def _create_llm(self, agent_config: Dict[str, Any]) -> Any:
        """Resolve LLM provider OR create a Consensus Swarm if --ai-swarm is active."""
        swarm_models = self.config.get('scan', {}).get('ai_swarm')
        if swarm_models:
            self.logger.info(
                f"🧠 [Unified Swarm] Initializing Consensus Engine with: {swarm_models}"
            )
            model_list = [m.strip() for m in swarm_models.split(',')]
            return ConsensusLLM(model_list, self, self.config, self.logger)

        model = agent_config.get('model', self.config['llm']['default_model'])
        return self._instantiate_single_llm(model, agent_config.get('temperature', 0.2))

    def _instantiate_single_llm(self, model: str, temperature: float) -> Any:
        api_key: Optional[str] = None
        provider: Optional[str] = None
        for prefixes, prov, key_name in _MODEL_PROVIDER_MAP:
            if any(model.startswith(p) for p in prefixes):
                provider = prov
                api_key = self.config['llm'].get(key_name)
                break

        if provider == 'anthropic':
            return ChatAnthropic(model=model, api_key=api_key, temperature=temperature)
        elif provider == 'google':
            return ChatGoogleGenerativeAI(
                model=model, google_api_key=api_key, temperature=temperature
            )
        elif provider == 'deepseek':
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url="https://api.deepseek.com/v1",
                temperature=temperature,
            )
        else:
            return ChatOpenAI(
                model=model,
                api_key=api_key or self.config['llm'].get('openai_api_key'),
                temperature=temperature,
            )

    # ── Phase Dispatcher ──────────────────────────────────────────────────────
    def run_phase(self, phase_name: str, context: Dict[str, Any]) -> Any:
        """Execute a specific phase of the scanning workflow with error handling."""
        self.logger.info(f"AgentController starting phase: {phase_name}")
        tci_score = context.get('tci_score', 0)

        try:
            # Merge persistent memory into context if data is missing
            if phase_name == "enrichment" and not context.get('subdomains'):
                subs = [n['value'] for _, n in self.memory_graph.query(type='subdomain')]
                if subs:
                    context['subdomains'] = subs
                    self.logger.debug(f"Loaded {len(subs)} subdomains from memory graph")

            if phase_name == "web_recon" and not context.get('live_hosts'):
                hosts = [n['value'] for _, n in self.memory_graph.query(type='live_host')]
                if hosts:
                    context['live_hosts'] = hosts
                    self.logger.debug(f"Loaded {len(hosts)} live hosts from memory graph")

            if phase_name == "vuln_scan":
                subs = [n['value'] for _, n in self.memory_graph.query(type='subdomain')]
                hosts = [n['value'] for _, n in self.memory_graph.query(type='live_host')]
                context.setdefault('subdomains', subs)
                context.setdefault('live_hosts', hosts)

            agents: List[Any] = []
            tasks: List[Any] = []

            phase_map = {
                "discovery":  self._build_discovery_phase,
                "enrichment": self._build_enrichment_phase,
                "web_recon":  self._build_web_recon_phase,
                "vuln_scan":  self._build_vuln_scan_phase,
                "validation": self._build_validator_phase,
                "reporting":  self._build_reporter_phase,
            }

            builder = phase_map.get(phase_name)
            if builder is None:
                self.logger.error(f"Unknown phase: {phase_name}")
                return {}

            agents, tasks = builder(context)

            if not agents or not tasks:
                self.logger.warning(f"Phase {phase_name} has no agents or tasks")
                return {}

            crew = Crew(
                agents=agents,
                tasks=tasks,
                process=Process.sequential,
                verbose=True,
                cache=True,
            )
            result = crew.kickoff()

            try:
                self.memory_graph.save()
            except Exception as exc:
                self.logger.error(f"Failed to save memory graph: {exc}")

            return self._parse_phase_result(result, phase_name)

        except Exception as exc:
            self.logger.error(
                f"Error during {phase_name} phase execution: {type(exc).__name__} - {exc}", exc_info=True
            )
            return {}

    # ── Phase Builders ────────────────────────────────────────────────────────
    def _tci_note(self, context: Dict[str, Any]) -> str:
        """Return a TCI context note to inject into every agent task description."""
        score = context.get('tci_score', 0)
        band  = context.get('tci_band', 'UNKNOWN')
        if score >= 75:
            return (
                f"\n\n[TCI: {score}/100 — {band}] "
                "This is a HIGH-COMPLEXITY target. Use ALL available tools, "
                "enumerate exhaustively, and chain every vulnerability primitive."
            )
        if score >= 40:
            return (
                f"\n\n[TCI: {score}/100 — {band}] "
                "MEDIUM-COMPLEXITY target. Focus on sensitive endpoints and APIs."
            )
        return (
            f"\n\n[TCI: {score}/100 — {band}] "
            "LOW-COMPLEXITY target. Prioritize quick, high-confidence findings."
        )

    def _build_discovery_phase(
        self, context: Dict[str, Any]
    ) -> Tuple[List[Any], List[Any]]:
        planner = Agent(
            role='Discovery Specialist',
            goal=(
                'Identify ALL attack surface assets: domains, subdomains, IPs, '
                'and cloud resources associated with the target.'
            ),
            backstory=(
                'Expert OSINT investigator with deep knowledge in DNS enumeration, '
                'WHOIS analysis, ASN lookups, and public repository metadata extraction. '
                'You map the broadest possible attack surface before any active testing.'
            ),
            tools=self.tool_registry.get_tools('discovery'),
            llm=self._create_llm(self.config['agents']['planner']),
        )
        task = Task(
            description=(
                f"Perform deep discovery for target: {context.get('target')}. "
                "Use subfinder, amass, assetfinder, and OSINT tools to find all "
                "related subdomains and IP addresses. Store all discovered assets "
                "in memory for downstream phases."
                + self._tci_note(context)
            ),
            agent=planner,
            expected_output=(
                "A structured JSON object with 'subdomains' (list of strings) and "
                "'ips' (list of strings) found during discovery."
            ),
        )
        return [planner], [task]

    def _build_enrichment_phase(
        self, context: Dict[str, Any]
    ) -> Tuple[List[Any], List[Any]]:
        recon = Agent(
            role='Enrichment Specialist',
            goal=(
                'Validate subdomains and enrich them with network metadata: '
                'DNS records, SSL/TLS certs, open ports, and running services.'
            ),
            backstory=(
                'Technical infrastructure auditor specializing in verifying asset '
                'liveness using dnsx and puredns, and profiling services via nmap '
                'and tlsx. You produce actionable host profiles.'
            ),
            tools=self.tool_registry.get_tools('hosts'),
            llm=self._create_llm(self.config['agents']['recon']),
        )
        task = Task(
            description=(
                f"Validate these subdomains and identify live hosts: "
                f"{context.get('subdomains')}. "
                "For each live host: perform port scanning, service fingerprinting, "
                "and SSL/TLS analysis. Record all live hosts in memory."
                + self._tci_note(context)
            ),
            agent=recon,
            expected_output=(
                "A JSON object with 'live_hosts' (list of URLs) and 'port_data' "
                "(dict mapping host → open ports)."
            ),
        )
        return [recon], [task]

    def _build_web_recon_phase(
        self, context: Dict[str, Any]
    ) -> Tuple[List[Any], List[Any]]:
        web_specialist = Agent(
            role='Web Recon Analyst',
            goal=(
                'Profile web technologies, crawl all endpoints, and identify '
                'the full hidden attack surface of every web application.'
            ),
            backstory=(
                'Expert in modern web architecture. Fingerprints tech stacks with '
                'CMSeeK and wafw00f. Discovers hidden endpoints via katana crawling '
                'and JS secret extraction. Maps every API and auth surface.'
            ),
            tools=self.tool_registry.get_tools('web'),
            llm=self._create_llm(self.config['agents']['recon']),
        )
        task = Task(
            description=(
                f"Analyze tech stacks and endpoints for live hosts: "
                f"{context.get('live_hosts')}. "
                "Fingerprint frameworks, extract JS files for secrets/tokens, "
                "discover hidden directories and APIs. Output all endpoints found."
                + self._tci_note(context)
            ),
            agent=web_specialist,
            expected_output=(
                "A JSON object with 'tech_stack' (list), 'endpoints' (list of URLs), "
                "and 'js_findings' (list of detected secrets or tokens)."
            ),
        )
        return [web_specialist], [task]

    def _build_vuln_scan_phase(
        self, context: Dict[str, Any]
    ) -> Tuple[List[Any], List[Any]]:
        exploit_cfg = self.config['agents'].get(
            'exploit', self.config['agents'].get('recon', {})
        )

        strategist = Agent(
            role='Lead Attack Strategist',
            goal=(
                'Plan the optimal attack path. Prioritize high-value targets '
                'using TCI data and logical vulnerability chaining.'
            ),
            backstory=(
                'Expert red team strategist. Analyzes tech stack data, endpoint '
                'mappings, and exposed secrets to plan multi-stage attacks. '
                'Uses logical reasoning to chain vulnerabilities for maximum impact.'
            ),
            tools=(
                self.tool_registry.get_tools('discovery')
                + self.tool_registry.get_tools('web')
            ),
            llm=self._create_llm(exploit_cfg),
            allow_delegation=True,
        )
        generator = Agent(
            role='Elite Payload Architect',
            goal=(
                'Generate highly-targeted, context-aware payloads and custom '
                'exploit scripts for each identified vulnerability class.'
            ),
            backstory=(
                "Specialized in precision exploitation. Doesn't use generic payloads — "
                "studies the target stack (PHP, Go, Node) and crafts custom bypasses. "
                "Uses the sandbox terminal and browser to verify payload execution."
            ),
            tools=self.tool_registry.get_tools('vuln'),
            llm=self._create_llm(exploit_cfg),
        )
        interpreter = Agent(
            role='Senior Vulnerability Interpreter',
            goal=(
                'Analyze tool outputs, identify root causes, filter false positives, '
                'and assign industrial-grade CVSS v3.1 severity scores.'
            ),
            backstory=(
                'Security auditor and CVSS expert. Transforms raw data into elite '
                'technical reports. Explains why something is broken and provides '
                'code-level remediation. Maintains zero hallucinations.'
            ),
            tools=[],  # Pure reasoning role
            llm=self._create_llm(exploit_cfg),
        )

        task_strategy = Task(
            description=(
                f"Analyze the full attack surface: {json.dumps(context)}. "
                "Prioritize which endpoints and services to exploit first. "
                "Create a sequential ATTACK PLAN with reasoning for each choice."
                + self._tci_note(context)
            ),
            agent=strategist,
            expected_output="A prioritized attack plan with targets and planned vectors.",
        )
        task_generation = Task(
            description=(
                "Execute tools and generate payloads for targets in the attack plan. "
                "Use the sandbox terminal and browser automation to verify execution. "
                "Focus on bypasses, logical flaws, and business-logic vulnerabilities."
            ),
            agent=generator,
            context=[task_strategy],
            expected_output=(
                "A technical list of vulnerabilities with context-aware payloads "
                "and execution evidence."
            ),
        )
        task_analysis = Task(
            description=(
                "Interpret the exploitation results. For each confirmed finding: "
                "1. Explain ROOT CAUSE. 2. Filter false positives. "
                "3. Assign CVSS v3.1 score with full vector string. "
                "4. Provide code-level remediation.\n\n"
                "Output a valid JSON array of findings matching this schema:\n"
                '{"title","severity","cvss_score","cvss_vector","root_cause",'
                '"impact","location","description","payload","method",'
                '"poc_lang","poc","remediation"}'
            ),
            agent=interpreter,
            context=[task_generation],
            expected_output=(
                "A JSON array of findings with title, severity, cvss_score, "
                "cvss_vector, root_cause, attack_payload, poc, and remediation."
            ),
        )
        return (
            [strategist, generator, interpreter],
            [task_strategy, task_generation, task_analysis],
        )

    def _build_validator_phase(
        self, context: Dict[str, Any]
    ) -> Tuple[List[Any], List[Any]]:
        """Dedicated Validator Agent — confirms findings with mutated payloads."""
        exploit_cfg = self.config['agents'].get(
            'exploit', self.config['agents'].get('recon', {})
        )
        validator = Agent(
            role='Elite Validation Specialist',
            goal=(
                'Confirm or deny every security finding with ZERO false positives. '
                'Every confirmed finding must have a reproducible PoC.'
            ),
            backstory=(
                'You are the final quality gate for BBH-AI. '
                'Your job is to independently reproduce every finding using a '
                'MUTATED variant of the original payload — never accept the tool '
                'output at face value. If you cannot reproduce it, it is NOT a finding.'
            ),
            tools=self.tool_registry.get_tools('vuln'),
            llm=self._create_llm(exploit_cfg),
        )
        findings = context.get('findings', [])
        tci_score = context.get('tci_score', 0)
        task = Task(
            description=(
                f"Validate these {len(findings)} findings for target "
                f"'{context.get('target', 'unknown')}' "
                f"(TCI: {tci_score}/100).\n\n"
                f"Findings to validate:\n{json.dumps(findings, indent=2)}\n\n"
                "For EACH finding:\n"
                "1. MUTATE the payload slightly (URL encode, case swap, comment append)\n"
                "2. RE-EXECUTE it via the sandbox and check the response\n"
                "3. If confirmed: set confirmed=true and populate poc_python + poc_curl\n"
                "4. If NOT confirmed after 2 mutation attempts: set confirmed=false\n\n"
                "Output ONLY a valid JSON array, one object per finding:\n"
                '{"confirmed","title","severity","cvss_score","cvss_vector",'
                '"root_cause","impact","remediation","location","payload",'
                '"poc_curl","poc_python"}'
            ),
            agent=validator,
            expected_output=(
                "A JSON array of validated findings with confirmed status, "
                "CVSS scores, and executable PoC scripts."
            ),
        )
        return [validator], [task]

    def _build_reporter_phase(
        self, context: Dict[str, Any]
    ) -> Tuple[List[Any], List[Any]]:
        """Dedicated Reporter Agent — compiles final executive-quality report data."""
        reporter_cfg = self.config['agents'].get('reporter', {})
        reporter = Agent(
            role='Senior Security Reporter',
            goal=(
                'Compile all validated findings into an executive-level, '
                'developer-friendly security report with actionable remediation.'
            ),
            backstory=(
                'You write security reports that non-technical executives and '
                'developers both understand. Every finding must have a clear '
                'business impact statement, code-level root cause, and step-by-step '
                'remediation. No jargon without explanation.'
            ),
            tools=[],  # Pure reasoning / compilation role
            llm=self._create_llm(reporter_cfg),
        )
        findings = context.get('findings', [])
        task = Task(
            description=(
                f"Compile {len(findings)} confirmed security findings for "
                f"'{context.get('target', 'unknown')}' into a final report.\n\n"
                "For each finding ensure:\n"
                "1. description — human-readable explanation without acronym jargon\n"
                "2. root_cause — technical explanation of the underlying code flaw\n"
                "3. impact — business risk statement (data breach, account takeover, etc.)\n"
                "4. remediation — numbered step-by-step fix with code examples\n"
                "5. cvss_score + cvss_vector — CVSS v3.1 if not already assigned\n\n"
                "Sort findings by severity (critical → high → medium → low → info).\n"
                "Output a valid JSON array of enriched finding objects."
            ),
            agent=reporter,
            expected_output=(
                "A JSON array of fully documented findings sorted by severity, "
                "ready for direct inclusion in the final report."
            ),
        )
        return [reporter], [task]

    # ── Result Parsing ────────────────────────────────────────────────────────
    def _parse_phase_result(self, result: Any, phase_name: str) -> Any:
        """Standardise crew output back into a dictionary."""
        raw = str(result)

        if phase_name in ("vuln_scan", "validation", "reporting"):
            return {"findings": self._extract_findings(result)}

        try:
            data = json.loads(raw)
            parsed = data if isinstance(data, dict) else {"results": data}

            # Persist to MemoryGraph for cross-phase data sharing
            if phase_name == "discovery" and "subdomains" in parsed:
                for sub in parsed["subdomains"]:
                    self.memory_graph.add_node(f"sub:{sub}", {"type": "subdomain", "value": sub})
            if phase_name == "enrichment" and "live_hosts" in parsed:
                for host in parsed["live_hosts"]:
                    self.memory_graph.add_node(f"host:{host}", {"type": "live_host", "value": host})
            if phase_name == "web_recon":
                for ep in parsed.get("endpoints", []):
                    self.memory_graph.add_node(f"ep:{ep}", {"type": "endpoint", "value": ep})

            self.memory_graph.save()
            return parsed
        except (json.JSONDecodeError, ValueError, TypeError):
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
            if isinstance(data, dict):
                if 'findings' in data and isinstance(data['findings'], list):
                    return self._normalise_findings(data['findings'])
                return self._normalise_findings([data])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # Strategy 2: Extract JSON array buried inside text/markdown
        json_match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    return self._normalise_findings(data)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        # Strategy 3: Single finding dict match
        dict_match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if dict_match:
            try:
                data = json.loads(dict_match.group())
                return self._normalise_findings([data])
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        self.logger.warning("Could not parse findings as JSON. Returning raw as info.")
        return [{
            'title':       'Unparsed Agent Output',
            'severity':    'info',
            'location':    'N/A',
            'description': raw[:2000],
            'validated':   False,
        }]

    def _normalise_findings(self, findings: List[Any]) -> List[Dict[str, Any]]:
        """Ensure every finding dict has all required keys with safe defaults."""
        required_keys: Dict[str, Any] = {
            'title':       'Unknown Finding',
            'severity':    'info',
            'cvss_score':  0.0,
            'cvss_vector': '',
            'root_cause':  'Not specified.',
            'location':    'N/A',
            'description': 'No description provided.',
            'impact':      'Vulnerability impact not specified.',
            'remediation': 'No remediation steps provided.',
            'payload':     '',
            'poc_lang':    'text',
            'poc':         '',
            'poc_python':  '',
            'poc_curl':    '',
            'validated':   False,
        }
        normalised = []
        for f in findings:
            if isinstance(f, dict):
                entry = {k: f.get(k, required_keys[k]) for k in required_keys}
                if entry.get('payload') and not entry.get('poc'):
                    entry['poc'] = f"Payload: {entry['payload']}"
                normalised.append(entry)
        return normalised


# ── Consensus Swarm ───────────────────────────────────────────────────────────
class ConsensusLLM:
    """
    Ensemble LLM Wrapper implementing 'Unified AI' logic where multiple
    models deliberate to reach a high-confidence security analysis consensus.
    """

    def __init__(
        self,
        models: List[str],
        controller: AgentController,
        config: Dict[str, Any],
        logger: logging.Logger,
    ):
        self.models = models
        self.config = config
        self.logger = logger
        self.llms: List[Any] = []
        for m in models:
            try:
                self.llms.append(controller._instantiate_single_llm(m, 0.2))
            except Exception as exc:
                self.logger.warning(f"Could not instantiate swarm member {m}: {exc}")

    def invoke(self, prompt: Any) -> Any:
        """Query all models and perform consensus refinement via Governor Synthesis."""
        llm_timeout = self.config.get('llm', {}).get('timeout_seconds', 60)
        responses: List[Dict[str, str]] = []

        for llm in self.llms:
            try:
                start = time.time()
                response = str(llm.invoke(prompt))
                elapsed = time.time() - start
                model_name = getattr(llm, 'model', 'unknown')
                if elapsed > llm_timeout:
                    self.logger.warning(
                        f"Swarm member {model_name} exceeded timeout "
                        f"({elapsed:.1f}s > {llm_timeout}s) — included anyway"
                    )
                responses.append({"model": model_name, "response": response})
            except Exception as exc:
                model_name = getattr(llm, 'model', 'unknown')
                self.logger.error(f"Swarm member {model_name} failed: {exc}")

        if not responses:
            raise ValueError("All swarm members failed.")
        if len(responses) == 1:
            return responses[0]["response"]

        refinement_prompt = (
            "### SWARM CONSENSUS — GOVERNOR SYNTHESIS ###\n"
            "You are the Governor Model for the BBH-AI Swarm.\n"
            "Multiple independent security analyses are provided below.\n\n"
            "STRICT RULES:\n"
            "1. REASON_FIRST: Analyse inputs step-by-step before concluding.\n"
            "2. CONTRADICTION_CHECK: Explicitly note where models disagree.\n"
            "3. WEIGHTED_TRUST: Resolve contradictions by favouring the most "
            "technically detailed proof with a specific payload or location.\n"
            "4. HALLUCINATION_GUARD: Mark any finding without a specific payload "
            "or location as 'speculative'.\n"
            "5. CVSS_SCORING: Provide a justified CVSS v3.1 score (score + vector) "
            "for each confirmed finding.\n"
            "6. ROOT_CAUSE: Explain the underlying code/config flaw.\n\n"
            "Raw Swarm Inputs:\n"
            + "\n".join(
                f"--- Model: {r['model']} ---\n{r['response']}" for r in responses
            )
            + "\n\nFinal Consolidated Analysis (Reasoning → Finding → Fix):"
        )

        # Governor: prefer Claude for reasoning, fall back to first LLM
        governor = next(
            (llm for llm in self.llms
             if hasattr(llm, 'model') and 'claude' in llm.model.lower()),
            self.llms[0] if self.llms else None,
        )
        if not governor:
            raise RuntimeError("No LLMs available for governor synthesis")

        governor_name = getattr(governor, 'model', 'Governor')
        self.logger.info(
            f"🧠 [Swarm Governor] {governor_name} synthesizing consensus..."
        )
        try:
            return governor.invoke(refinement_prompt)
        except Exception as exc:
            self.logger.error(f"Governor synthesis failed: {exc}")
            return "\n---\n".join(r["response"] for r in responses)
