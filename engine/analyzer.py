"""
engine/analyzer.py — Hybrid AI-Tool Vulnerability Analyzer

Implements the flow:
  Tool Output → AI Interpretation → Sandbox Validation → PoC Generation → Final Report
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from validation.poc_generator import PoCGenerator


class VulnerabilityAnalyzer:
    """
    Hybrid AI-Tool Vulnerability Engine for BBH-AI.
    Interprets raw tool output, validates findings via sandbox, and attaches
    auto-generated PoC scripts to every confirmed vulnerability.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        agent_controller: Any,
        tool_registry: Any,
        sandbox_client: Any = None,
    ):
        self.config = config
        self.agent_controller = agent_controller
        self.tool_registry = tool_registry
        # sandbox can be passed explicitly or retrieved from config
        self.sandbox = sandbox_client or config.get('_sandbox_client')
        self.logger = logging.getLogger(__name__)
        self.poc_gen = PoCGenerator()

    async def analyze_finding(
        self,
        tool_name: str,
        output: Any,
        target: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Takes raw tool output, interprets it using AI, validates via sandbox,
        and attaches auto-generated PoC scripts.
        """
        self.logger.info(
            f"🔬 [VulnerabilityAnalyzer] Analyzing finding from {tool_name} for: {target}"
        )

        # 1. AI Interpretation
        interpretation = await self._interpret_output(tool_name, output, target)
        if not interpretation or interpretation.get('is_false_positive'):
            self.logger.info(
                f"🚫 [VulnerabilityAnalyzer] AI marked {tool_name} finding as False Positive."
            )
            return None

        # 2. Sandbox Validation
        if interpretation.get('validation_required'):
            validated = await self._validate_finding(interpretation, target)
            if not validated:
                self.logger.warning(
                    f"⚠️  Validation failed for: {interpretation.get('title')}"
                )
                return None
            interpretation = validated

        # 3. PoC Generation
        interpretation = self._attach_poc(interpretation)

        return interpretation

    async def _interpret_output(
        self,
        tool_name: str,
        output: Any,
        target: str,
    ) -> Optional[Dict[str, Any]]:
        """Use LLMs to interpret raw tool output."""
        raw_output = (
            json.dumps(output, indent=2)
            if isinstance(output, (dict, list))
            else str(output)
        )

        prompt = f"""\
You are a Senior Security Analyst at a professional bug-bounty firm.

Analyze the output of the tool '{tool_name}' for target '{target}'.

Raw Tool Output:
{raw_output}

TASK:
1. Determine if this is a REAL vulnerability or a false positive.
2. Explain the ROOT CAUSE of the vulnerability.
3. Generate a tailored ATTACK PAYLOAD to verify it.
4. Calculate a CVSS 3.1 Severity Score with full vector justification.
5. Provide a clear REMEDIATION plan (code-level where possible).

Output ONLY valid JSON matching this schema exactly:
{{
    "title":              "...",
    "severity":           "critical|high|medium|low|info",
    "cvss_score":         0.0,
    "cvss_vector":        "AV:.../AC:.../PR:.../UI:.../S:.../C:.../I:.../A:...",
    "root_cause":         "...",
    "impact":             "...",
    "attack_payload":     "...",
    "method":             "GET|POST",
    "location":           "...",
    "remediation":        "...",
    "is_false_positive":  false,
    "validation_required": true
}}
"""
        try:
            response = await self.agent_controller._create_llm({}).ainvoke(prompt)
            json_match = re.search(r'\{.*\}', str(response), re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as exc:
            self.logger.error(f"❌ [VulnerabilityAnalyzer] Interpretation failure: {exc}")
            return None

    async def _validate_finding(
        self,
        interpretation: Dict[str, Any],
        target: str,
    ) -> Optional[Dict[str, Any]]:
        """Validate via sandbox using the AI-suggested attack payload."""
        payload = interpretation.get('attack_payload', '')
        poc_lang = interpretation.get('poc_lang', 'bash')

        if not payload:
            self.logger.debug("No payload provided for validation — marking unvalidated")
            interpretation['validated'] = False
            return interpretation

        try:
            self.logger.info(
                f"🧪 [VulnerabilityAnalyzer] Validating: {payload[:60]}..."
            )
            if self.sandbox and getattr(self.sandbox, 'enabled', False):
                try:
                    if poc_lang.lower() in ('bash', 'sh', 'shell'):
                        result = await self.sandbox.execute_bash(payload, timeout=30)
                    elif poc_lang.lower() == 'python':
                        result = await self.sandbox.execute_python(payload, timeout=30)
                    else:
                        self.logger.warning(
                            f"Unsupported PoC language: {poc_lang!r}, skipping sandbox validation"
                        )
                        interpretation['validated'] = False
                        return interpretation

                    interpretation['validated'] = bool(
                        result.get('success', False) if result else False
                    )
                    interpretation['validation_result'] = result
                except Exception as exc:
                    self.logger.debug(f"Sandbox validation error: {exc}")
                    interpretation['validated'] = False
            else:
                self.logger.debug("Sandbox not available — marking unvalidated")
                interpretation['validated'] = False

            return interpretation
        except Exception as exc:
            self.logger.error(f"Validation execution failed: {exc}")
            interpretation['validated'] = False
            return interpretation

    def _attach_poc(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        """Generate and attach Python + cURL PoC scripts to the finding."""
        try:
            finding['poc_python'] = self.poc_gen.generate_python_poc(finding)
            finding['poc_curl']   = self.poc_gen.generate_curl_poc(finding)
            # Legacy field used by older report templates
            finding['poc_lang'] = finding.get('poc_lang') or 'python'
            if not finding.get('poc'):
                finding['poc'] = finding['poc_python']
        except Exception as exc:
            self.logger.warning(f"PoC generation failed: {exc}")
        return finding
