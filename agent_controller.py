import logging
import json
import re
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import signal

# CrewAI & LangChain Imports
try:
    from crewai import Agent, Task, Crew, Process
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    pass

from memory.graph import MemoryGraph

# Maps model name prefixes to their provider + config key
_MODEL_PROVIDER_MAP: List[Tuple[Tuple[str, ...], str, str]] = [
    (('gpt-',),               'openai',    'openai_api_key'),
    (('claude-',),            'anthropic', 'anthropic_api_key'),
    (('gemini-',),            'google',    'google_api_key'),
    (('deepseek-',),          'deepseek',  'openai_api_key'), # DeepSeek uses OpenAI wrapper usually
    (('o1-', 'o3-', 'o4-'),   'openai',    'openai_api_key'),
]


class AgentController:
    def __init__(self, config: Dict[str, Any], workspace: Any, telemetry: Any, tool_registry: Any):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.tool_registry = tool_registry
        
        # Initialize MemoryGraph with persistence
        graph_path = Path(workspace) / "memory_graph.json" if workspace else None
        self.memory_graph = MemoryGraph(graph_path)
        
        self.logger = logging.getLogger(__name__)

    def _create_llm(self, agent_config: Dict[str, Any]) -> Any:
        """Resolve LLM provider OR create a Consensus Swarm if --ai is active."""
        swarm_models = self.config.get('scan', {}).get('ai_swarm')
        
        if swarm_models:
            self.logger.info(f"🧠 [Unified Swarm] Initializing Consensus Engine with: {swarm_models}")
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
            return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature)
        elif provider == 'deepseek':
            return ChatOpenAI(model=model, api_key=api_key, base_url="https://api.deepseek.com/v1", temperature=temperature)
        else:
            # Default to OpenAI
            return ChatOpenAI(model=model, api_key=api_key or self.config['llm'].get('openai_api_key'), temperature=temperature)

class ConsensusLLM:
    """
    Ensemble LLM Wrapper. Implements "Unified AI" logic where multiple 
    models deliberate to reach a high-confidence consensus.
    """
    def __init__(self, models: List[str], controller: AgentController, config: Dict[str, Any], logger: logging.Logger):
        self.models = models
        self.config = config
        self.logger = logger
        self.llms = []
        for m in models:
            try:
                llm = controller._instantiate_single_llm(m, 0.2)
                self.llms.append(llm)
            except Exception as e:
                self.logger.warning(f"Could not instantiate swarm member {m}: {e}")

    def invoke(self, prompt: Any) -> Any:
        """Query all models and perform consensus refinement with Governor Synthesis."""
        llm_timeout = self.config.get('llm', {}).get('timeout_seconds', 60)
        responses = []
        
        for llm in self.llms:
            try:
                self.logger.debug(f"Swarm member {llm.model} deliberating... (timeout: {llm_timeout}s)")
                # Set timeout for LLM invocation - most LLM clients support request_timeout
                start_time = time.time()
                response = str(llm.invoke(prompt))
                elapsed = time.time() - start_time
                
                if elapsed > llm_timeout:
                    self.logger.warning(f"Swarm member {llm.model} exceeded timeout ({elapsed:.1f}s > {llm_timeout}s)")
                else:
                    responses.append({"model": llm.model, "response": response})
            except Exception as e:
                self.logger.error(f"Swarm member {llm.model} failed: {e}")

        if not responses:
            raise ValueError("All swarm members failed.")

        if len(responses) == 1:
            return responses[0]["response"]

        # High-IQ Synthesis Prompt (Claude-style Reasoning Integrated)
        refinement_prompt = f"""
### SWARM CONSENSUS CHALLENGE: GOVERNOR SYNTHESIS ###
You are the Governor Model for the BBH-AI Swarm. 
Below are multiple independent security analyses of the same target. 

STRICT REASONING RULES:
1. REASON_FIRST: Before providing the final result, you MUST analyze the inputs step-by-step.
2. CONTRADICTION_CHECK: Explicitly identify where models disagree.
3. WEIGHTED_TRUST: Resolve contradictions by favoring the most technically detailed proof.
4. HALLUCINATION_GUARD: If a finding lacks a specific payload or location, mark it as 'speculative'.
5. CVSS_SCORING: Provide a justified CVSS v3.1 score for each confirmed finding.
6. ROOT_CAUSE: Explain the underlying code/config flaw for each vulnerability.

Raw Swarm Inputs:
{chr(10).join(f"--- Model: {r['model']} ---\n{r['response']}" for r in responses)}

Final Consolidated Analysis (Follow the 'Reasoning -> Finding -> Fix' format):
"""
        # Use strongest available model for governor synthesis
        # Prefer Claude (reasoning best), then GPT-4, then fallback to first available
        governor = None
        for llm in self.llms:
            if hasattr(llm, 'model') and 'claude' in llm.model.lower():
                governor = llm
                break
        if not governor and self.llms:
            # Fallback to first LLM if no Claude available
            governor = self.llms[0]
        
        if not governor:
            raise RuntimeError("No LLMs available for governor synthesis")
        
        self.logger.info(f"🧠 [Swarm Governor] {governor.model if hasattr(governor, 'model') else 'Governor'} is synthesizing consensus with CoT Reasoning...")
        try:
            start_time = time.time()
            result = governor.invoke(refinement_prompt)
            elapsed = time.time() - start_time
            if elapsed > llm_timeout:
                self.logger.warning(f"Governor synthesis exceeded timeout ({elapsed:.1f}s > {llm_timeout}s)")
            return result
        except Exception as e:
            self.logger.error(f"Governor synthesis failed: {e}")
            # Fallback: return concatenated swarm responses if synthesis fails
            return "\n---\n".join(r["response"] for r in responses)

    def run(self, attack_surface: Any) -> Dict[str, Any]:
        """Legacy compatibility method for single-run scans."""
        return self.run_phase("full", attack_surface)

    def run_phase(self, phase_name: str, context: Dict[str, Any]) -> Any:
        """Execute a specific phase of the scanning workflow with error handling."""
        self.logger.info(f"AgentController starting phase: {phase_name}")
        
        try:
            # Merge persistent memory into context if data is missing
            if phase_name == "enrichment" and not context.get('subdomains'):
                subdomains = [n['value'] for _, n in self.memory_graph.query(type='subdomain')]
                if subdomains:
                    context['subdomains'] = subdomains
                    self.logger.debug(f"Loaded {len(subdomains)} subdomains from memory graph")
            
            if phase_name == "web_recon" and not context.get('live_hosts'):
                live_hosts = [n['value'] for _, n in self.memory_graph.query(type='live_host')]
                if live_hosts:
                    context['live_hosts'] = live_hosts
                    self.logger.debug(f"Loaded {len(live_hosts)} live hosts from memory graph")
            
            if phase_name == "vuln_scan":
                # Vuln scan needs full context, pulling all known assets
                subdomains = [n['value'] for _, n in self.memory_graph.query(type='subdomain')]
                live_hosts = [n['value'] for _, n in self.memory_graph.query(type='live_host')]
                if subdomains:
                    context.setdefault('subdomains', subdomains)
                if live_hosts:
                    context.setdefault('live_hosts', live_hosts)
            
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
            
            # Persist memory after phase completion
            try:
                self.memory_graph.save()
            except Exception as e:
                self.logger.error(f"Failed to save memory graph: {e}")
            
            return self._parse_phase_result(result, phase_name)
        
        except Exception as e:
            self.logger.error(f"Error during {phase_name} phase execution: {e}", exc_info=True)
            return {}

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
        # 1. THE ATTACK STRATEGIST (Planning)
        strategist = Agent(
            role='Lead Attack Strategist',
            goal='Plan the optimal attack path based on reconnaissance data. Identify high-value targets and logical flows.',
            backstory='Expert red team strategist. You analyze technical stack data, endpoint mappings, and JS secrets to prioritize targets. You use logical reasoning to plan how to chain vulnerabilities.',
            tools=self.tool_registry.get_tools('discovery') + self.tool_registry.get_tools('web'),
            llm=self._create_llm(self.config['agents'].get('exploit', self.config['agents'].get('recon', {}))),
            allow_delegation=True
        )

        # 2. THE PAYLOAD GENERATOR (Exploitation)
        generator = Agent(
            role='Elite Payload Architect',
            goal='Generate highly-targeted, context-aware payloads and custom exploit scripts for identified targets.',
            backstory='Specialized in precision exploitation. You don\'t use generic payloads; you study the target stack (e.g., PHP, Go, Node) and craft custom bypasses. You use the sandbox to verify payload syntax.',
            tools=self.tool_registry.get_tools('vuln'),
            llm=self._create_llm(self.config['agents'].get('exploit', self.config['agents'].get('recon', {}))),
        )

        # 3. THE VULNERABILITY INTERPRETER (Analysis & Scoring)
        interpreter = Agent(
            role='Senior Vulnerability Interpreter',
            goal='Analyze tool outputs, identify root causes, filter false positives, and assign industrial severity scores (CVSS).',
            backstory='Security auditor and CVSS expert. Your role is to take raw data and turn it into elite technical reports. You explain *why* something is broken and how to fix it at the code level. You ensure zero hallucinations.',
            tools=[], # Pure reasoning role
            llm=self._create_llm(self.config['agents'].get('exploit', self.config['agents'].get('recon', {}))),
        )

        task_strategy = Task(
            description=f"Analyze the full attack surface context: {json.dumps(context)}. Prioritize which endpoints and services to target first. Create a sequential ATTACK PLAN.",
            agent=strategist,
            expected_output="A prioritized attack plan documenting targets and planned exploit vectors."
        )

        task_generation = Task(
            description="Execute tools and generate specific payloads/PoCs for targets in the attack plan. Use the sandbox to verify execution where possible. Focus on bypasses and logical flaws.",
            agent=generator,
            context=[task_strategy],
            expected_output="A technical list of discovered vulnerabilities with context-aware payloads and execution logs."
        )

        task_analysis = Task(
            description="Interpret the findings from the generator. For each confirmed vulnerability: 1. Explain the ROOT CAUSE. 2. Filter False Positives. 3. Assign CVSS v3.1 Severity. 4. Provide Code-Level Remediation.",
            agent=interpreter,
            context=[task_generation],
            expected_output="A final structured JSON array of findings with: title, severity, cvss_score, root_cause, attack_payload, poc, and remediation."
        )

        return [strategist, generator, interpreter], [task_strategy, task_generation, task_analysis]

    def _parse_phase_result(self, result: Any, phase_name: str) -> Any:
        """Standardize the crew output back into a dictionary."""
        raw = str(result)
        
        if phase_name == "vuln_scan":
            # For vulnerability scanning, we need structured findings
            return {"findings": self._extract_findings(result)}

        try:
            data = json.loads(raw)
            parsed = data if isinstance(data, dict) else {"results": data}
            
            # Store results in MemoryGraph for cross-worker persistence
            if phase_name == "discovery" and "subdomains" in parsed:
                for sub in parsed["subdomains"]:
                    self.memory_graph.add_node(f"sub:{sub}", {"type": "subdomain", "value": sub})
            if phase_name == "enrichment" and "live_hosts" in parsed:
                for host in parsed["live_hosts"]:
                    self.memory_graph.add_node(f"host:{host}", {"type": "live_host", "value": host})
            
            self.memory_graph.save()
            return parsed
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
            'cvss_score': 0.0,
            'root_cause': 'Not specified.',
            'location': 'N/A',
            'description': 'No description provided.',
            'impact': 'Vulnerability impact not specified.',
            'remediation': 'No remediation steps provided.',
            'payload': '',
            'poc_lang': 'text',
            'poc': '',
            'validated': False,
        }
        normalised = []
        for f in findings:
            if isinstance(f, dict):
                entry = {k: f.get(k, required_keys[k]) for k in required_keys}
                # Special case: if payload is present but poc is not, assume it's part of the PoC context
                if entry.get('payload') and not entry.get('poc'):
                    entry['poc'] = f"Payload: {entry['payload']}"
                normalised.append(entry)
        return normalised
