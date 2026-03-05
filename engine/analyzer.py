import logging
import json
from typing import Any, Dict, List, Optional

class VulnerabilityAnalyzer:
    """
    Hybrid AI-Tool Vulnerability Engine for BBH-AI.
    Implements the flow: Tool Output -> AI Interpretation -> Validation Tool -> Final Report.

    This component may perform active payload validation using the sandbox client.
    The sandbox reference is optional; if provided it will be used during the
    validation stage. If not, the analyzer will still function but will mark
    findings as unvalidated.
    """
    def __init__(self, config: Dict[str, Any], agent_controller: Any, tool_registry: Any, sandbox_client: Any = None):
        self.config = config
        self.agent_controller = agent_controller
        self.tool_registry = tool_registry
        # sandbox can be passed explicitly or retrieved from config (injected by Orchestrator)
        self.sandbox = sandbox_client or config.get('_sandbox_client')
        self.logger = logging.getLogger(__name__)

    async def analyze_finding(self, tool_name: str, output: Any, target: str) -> Optional[Dict[str, Any]]:
        """
        Takes raw tool output, interprets it using AI, and performs validation.
        """
        self.logger.info(f"🔬 [VulnerabilityAnalyzer] Analyzing finding from {tool_name} for: {target}")

        # 1. Interpretation Phase (AI Models)
        interpretation = await self._interpret_output(tool_name, output, target)
        if not interpretation or interpretation.get('is_false_positive'):
            self.logger.info(f"🚫 [VulnerabilityAnalyzer] AI identified finding from {tool_name} as False Positive.")
            return None

        # 2. Validation Phase (Tool Execution)
        if interpretation.get('validation_required'):
            validated_finding = await self._validate_finding(interpretation, target)
            if not validated_finding:
                self.logger.warning(f"⚠️ [VulnerabilityAnalyzer] Validation failed for: {interpretation.get('title')}")
                return None
            return validated_finding

        return interpretation

    async def _interpret_output(self, tool_name: str, output: Any, target: str) -> Optional[Dict[str, Any]]:
        """Use LLMs to interpret raw tool output."""
        prompt = f"""
You are a Senior Security Analyst. Analyze the output of the tool '{tool_name}' for target '{target}'.

Raw Tool Output:
{json.dumps(output, indent=2) if isinstance(output, (dict, list)) else output}

Task:
1. Determine if this represents a real vulnerability or a false positive.
2. Explain the ROOT CAUSE of the vulnerability.
3. Generate a tailored ATTACK PAYLOAD to verify it.
4. Calculate a CVSS 3.1 Severity Score with justification.
5. Provide a clear REMEDIATION plan.

Output your findings in JSON format:
{{
    "title": "...",
    "severity": "...",
    "cvss_score": 0.0,
    "root_cause": "...",
    "attack_payload": "...",
    "remediation": "...",
    "is_false_positive": false,
    "validation_required": true
}}
"""
        try:
            # Use Swarm Consensus for Interpretation
            response = await self.agent_controller._create_llm({}).ainvoke(prompt)
            # Parse JSON from response
            import re
            json_match = re.search(r'\{.*\}', str(response), re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            self.logger.error(f"❌ [VulnerabilityAnalyzer] Interpretation failure: {e}")
            return None

    async def _validate_finding(self, interpretation: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
        """Perform validation using the recommended attack payload with proper sandbox integration."""
        payload = interpretation.get('attack_payload')
        poc_lang = interpretation.get('poc_lang', 'bash')
        
        if not payload:
            self.logger.debug("No payload provided for validation")
            interpretation['validated'] = False
            return interpretation
        
        try:
            self.logger.info(f"🧪 [VulnerabilityAnalyzer] Validating with payload: {payload[:50]}...")
            
            # Use sandbox for validation if available
            if self.sandbox and hasattr(self.sandbox, 'enabled') and self.sandbox.enabled:
                try:
                    if poc_lang.lower() in ['bash', 'sh', 'shell']:
                        result = await self.sandbox.execute_bash(payload, timeout=30)
                    elif poc_lang.lower() == 'python':
                        result = await self.sandbox.execute_python(payload, timeout=30)
                    else:
                        self.logger.warning(f"Unsupported PoC language: {poc_lang}, skipping validation")
                        interpretation['validated'] = False
                        return interpretation
                    
                    interpretation['validated'] = result.get('success', False) if result else False
                    interpretation['validation_result'] = result
                except Exception as e:
                    self.logger.debug(f"Sandbox validation failed: {e}, marking as unvalidated")
                    interpretation['validated'] = False
            else:
                self.logger.debug("Sandbox not available for validation")
                interpretation['validated'] = False
            
            return interpretation
        except Exception as e:
            self.logger.error(f"Validation execution failed: {e}")
            interpretation['validated'] = False
            return interpretation
