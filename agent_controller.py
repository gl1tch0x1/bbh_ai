from crewai import Agent, Task, Crew, Process
from crewai.llm import LLM
import logging

class AgentController:
    def __init__(self, config, workspace, telemetry, tool_registry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.tool_registry = tool_registry
        self.memory = None  # Not used yet
        self.logger = logging.getLogger(__name__)

    def _create_llm(self, agent_config):
        provider = None
        api_key = None
        model = agent_config.get('model', self.config['llm']['default_model'])

        if 'gpt' in model:
            provider = 'openai'
            api_key = self.config['llm'].get('openai_api_key')
        elif 'claude' in model:
            provider = 'anthropic'
            api_key = self.config['llm'].get('anthropic_api_key')
        elif 'gemini' in model:
            provider = 'google'
            api_key = self.config['llm'].get('google_api_key')
        elif 'deepseek' in model:
            provider = 'deepseek'
            api_key = self.config['llm'].get('deepseek_api_key')
        else:
            self.logger.warning(f"Unknown model {model}, defaulting to openai")
            provider = 'openai'
            api_key = self.config['llm'].get('openai_api_key')

        if not api_key:
            self.logger.error(f"No API key for provider {provider}")
            raise ValueError(f"Missing API key for {provider}")

        return LLM(provider=provider, model=model, api_key=api_key, temperature=agent_config.get('temperature', 0.2))

    def run(self, attack_surface):
        agents = []
        tasks = []

        if self.config['agents']['planner']['enabled']:
            planner = Agent(
                role='Planner',
                goal='Create an attack plan based on the attack surface',
                tools=self.tool_registry.get_tools('planner'),
                llm=self._create_llm(self.config['agents']['planner']),
                verbose=True,
                memory=self.memory
            )
            agents.append(planner)
            plan_task = Task(
                description=f"Analyze this attack surface: {attack_surface}. Create a step-by-step testing plan.",
                agent=planner,
                expected_output="A JSON list of tasks with tool names and arguments."
            )
            tasks.append(plan_task)

        if self.config['agents']['recon']['enabled']:
            recon_agent = Agent(
                role='Recon Agent',
                goal='Enumerate all endpoints, parameters, and hidden assets',
                tools=self.tool_registry.get_tools('recon'),
                llm=self._create_llm(self.config['agents']['recon']),
                verbose=True,
                memory=self.memory
            )
            agents.append(recon_agent)
            recon_task = Task(
                description="Execute the recon tasks from the plan and update the memory with new endpoints.",
                agent=recon_agent,
                context=[plan_task] if 'plan_task' in locals() else [],
                expected_output="Updated attack surface with new findings."
            )
            tasks.append(recon_task)

        if self.config['agents']['exploit']['enabled']:
            exploit_agent = Agent(
                role='Exploit Agent',
                goal='Test for vulnerabilities using appropriate tools',
                tools=self.tool_registry.get_tools('exploit'),
                llm=self._create_llm(self.config['agents']['exploit']),
                verbose=True,
                memory=self.memory
            )
            agents.append(exploit_agent)
            exploit_task = Task(
                description="Run exploitation tasks, validate vulnerabilities, and store findings.",
                agent=exploit_agent,
                context=[recon_task] if 'recon_task' in locals() else [],
                expected_output="List of potential vulnerabilities."
            )
            tasks.append(exploit_task)

        if self.config['agents']['reporter']['enabled']:
            reporter_agent = Agent(
                role='Reporter',
                goal='Validate findings and generate PoCs',
                tools=self.tool_registry.get_tools('reporter'),
                llm=self._create_llm(self.config['agents']['reporter']),
                verbose=True,
                memory=self.memory
            )
            agents.append(reporter_agent)
            report_task = Task(
                description="Validate each finding, assign severity, and prepare final report.",
                agent=reporter_agent,
                context=[exploit_task] if 'exploit_task' in locals() else [],
                expected_output="Validated findings with PoC."
            )
            tasks.append(report_task)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            memory=self.memory,
            verbose=2
        )
        result = crew.kickoff()
        findings = self._extract_findings(result)
        return findings

    def _extract_findings(self, result):
        # Placeholder: parse the final task output into a list of finding dicts
        # In a real implementation, the reporter agent would return structured data.
        return []