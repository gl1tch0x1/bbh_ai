"""
engine/tci.py — Target Complexity Index (TCI)

Scores a target's attack surface from 0 to 100 and derives a recommended
scan depth so agents automatically calibrate their effort to the target.

Score bands:
  75–100  HIGH COMPLEXITY   → deep scan, all exploit primitives enabled
  40–74   MEDIUM COMPLEXITY → standard scan, targeted exploitation
   0–39   LOW COMPLEXITY    → quick scan, high-value findings only
"""

import math
import logging
from typing import Any, Dict, List, Optional


class TCICalculator:
    """
    Computes the Target Complexity Index (0–100) from attack-surface data
    collected during Phase A/B reconnaissance.
    """

    MAX_SCORE = 100

    # Technologies that raise exploitation complexity significantly
    HIGH_VALUE_TECH: frozenset = frozenset({
        'wordpress', 'drupal', 'joomla', 'magento',
        'laravel', 'django', 'rails', 'struts',
        'jenkins', 'jira', 'confluence', 'bitbucket',
        'grafana', 'kibana', 'elasticsearch', 'mongodb',
        'redis', 'mysql', 'postgresql', 'mssql', 'oracle',
        'spring', 'express', 'fastapi', 'flask',
    })

    # Endpoint path fragments indicating sensitive surfaces
    SENSITIVE_PATTERNS: tuple = (
        'login', 'auth', 'admin', 'api/', 'oauth',
        'token', 'jwt', 'upload', 'import', 'export',
        'webhook', 'graphql', 'rpc', 'payment', 'checkout',
        'password', 'reset', 'verify', 'account',
    )

    # JS / response keywords that suggest credential exposure
    SECRET_PATTERNS: tuple = (
        'api_key', 'apikey', 'secret', 'password', 'passwd',
        'credential', 'bearer', 'aws_access', 'private_key',
        'authorization', 'x-api-key',
    )

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    # ── Public API ────────────────────────────────────────────────────────────
    def analyze(
        self,
        target: str,
        live_hosts: Optional[List[str]] = None,
        tech_stack: Optional[List[str]] = None,
        endpoints: Optional[List[str]] = None,
        js_findings: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Compute TCI and return a rich context dict for downstream agents.

        Returns:
            {
                "score":       int   (0–100),
                "band":        str   ("LOW" | "MEDIUM" | "HIGH"),
                "description": str,
                "scan_depth":  str   ("quick" | "deep"),
                "breakdown":   dict  (per-dimension scores),
            }
        """
        hosts     = live_hosts or []
        stack     = tech_stack or []
        eps       = endpoints or []
        js_hits   = js_findings or []

        breadth  = self._score_surface_breadth(hosts, eps)   # 0-20
        tech     = self._score_tech_stack(stack)              # 0-20
        auth     = self._score_auth_complexity(eps)           # 0-25
        secrets  = self._score_secrets_exposure(js_hits)     # 0-20
        services = self._score_service_diversity(hosts)       # 0-15

        total = min(breadth + tech + auth + secrets + services, self.MAX_SCORE)

        result = {
            "score":       total,
            "band":        self._band(total),
            "description": self._description(total),
            "scan_depth":  self._scan_depth(total),
            "breakdown": {
                "surface_breadth":  breadth,
                "tech_stack":       tech,
                "auth_complexity":  auth,
                "secrets_exposure": secrets,
                "service_diversity": services,
            },
        }

        self.logger.info(
            f"[TCI] {target} scored {total}/100 ({result['band']}) — "
            f"recommended depth: {result['scan_depth']}"
        )
        return result

    # ── Scoring dimensions ────────────────────────────────────────────────────
    def _score_surface_breadth(self, hosts: List[str], endpoints: List[str]) -> int:
        """Up to 20 pts: logarithmic scaling of host + endpoint count."""
        host_pts = min(int(10 * math.log1p(len(hosts))), 10)
        ep_pts   = min(int(10 * math.log1p(len(endpoints))), 10)
        return host_pts + ep_pts

    def _score_tech_stack(self, tech_stack: List[str]) -> int:
        """Up to 20 pts: 4 pts per high-value technology detected."""
        found = {t.lower().strip() for t in tech_stack}
        matches = len(found & self.HIGH_VALUE_TECH)
        return min(matches * 4, 20)

    def _score_auth_complexity(self, endpoints: List[str]) -> int:
        """Up to 25 pts: 3 pts per endpoint matching a sensitive pattern."""
        score = 0
        for ep in endpoints:
            ep_lower = str(ep).lower()
            if any(pat in ep_lower for pat in self.SENSITIVE_PATTERNS):
                score += 3
        return min(score, 25)

    def _score_secrets_exposure(self, js_findings: List[str]) -> int:
        """Up to 20 pts: 5 pts per secret-like token found in JS/responses."""
        score = 0
        for finding in js_findings:
            finding_lower = str(finding).lower()
            if any(pat in finding_lower for pat in self.SECRET_PATTERNS):
                score += 5
        return min(score, 20)

    def _score_service_diversity(self, live_hosts: List[str]) -> int:
        """Up to 15 pts: more unique hosts = more attack surface."""
        return min(len(live_hosts) * 2, 15)

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _band(score: int) -> str:
        if score >= 75:
            return "HIGH"
        if score >= 40:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _scan_depth(score: int) -> str:
        if score >= 75:
            return "deep"
        if score >= 40:
            return "standard"
        return "quick"

    @staticmethod
    def _description(score: int) -> str:
        if score >= 75:
            return (
                "HIGH COMPLEXITY — Full deep scan with all exploit primitives "
                "active (browser, proxy, terminal, payload chaining)."
            )
        if score >= 40:
            return (
                "MEDIUM COMPLEXITY — Standard scan with targeted exploitation "
                "on high-value endpoints."
            )
        return (
            "LOW COMPLEXITY — Quick scan focusing only on confirmed high-value "
            "findings. Use --mode deep to override."
        )
