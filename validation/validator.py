import hashlib
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from tools.registry import ToolRegistry

# CVSS v3.1 base score ranges and representative vector strings per severity
_CVSS_DEFAULTS: Dict[str, Tuple[float, str]] = {
    "critical": (9.8,  "AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"),
    "high":     (7.5,  "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"),
    "medium":   (5.3,  "AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N"),
    "low":      (2.0,  "AV:L/AC:H/PR:L/UI:R/S:U/C:L/I:N/A:N"),
    "info":     (0.0,  "AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N"),
}


class Validator:
    """Validates, normalises, CVSS-scores, and deduplicates security findings."""

    CRITICAL_SEVERITIES: Set[str] = {'critical', 'high'}
    VALID_SEVERITIES: Set[str] = {'critical', 'high', 'medium', 'low', 'info'}

    def __init__(self, config: Dict[str, Any], workspace: Any, telemetry: Any):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def validate(
        self,
        finding: Dict[str, Any],
        tool_registry: Optional['ToolRegistry'] = None,
    ) -> Dict[str, Any]:
        """
        Validate and normalise a finding:
        - Normalise severity to lowercase.
        - Ensure all required keys are present with safe defaults.
        - Assign CVSS v3.1 score if not already set.
        - Mark invalid-severity findings as 'info'.
        - Set validation flag based on data completeness.
        """
        title = finding.get('title', 'Unknown')
        self.logger.info(f"Validating finding: {title}")

        # Normalise severity
        severity = str(finding.get('severity', 'info')).lower().strip()
        if severity not in self.VALID_SEVERITIES:
            self.logger.warning(
                f"Finding '{title}' has unrecognized severity '{severity}' "
                f"— defaulting to 'info'."
            )
            severity = 'info'
        finding['severity'] = severity

        # Ensure required keys exist with safe defaults
        required_keys: Dict[str, Any] = {
            'location':    'N/A',
            'description': 'No description provided.',
            'payload':     '',
            'poc_lang':    '',
            'poc':         '',
            'poc_python':  '',
            'poc_curl':    '',
            'title':       'Unknown Finding',
            'root_cause':  'Not specified.',
            'impact':      'Vulnerability impact not specified.',
            'remediation': 'No remediation steps provided.',
        }
        for key, default in required_keys.items():
            if key not in finding or finding[key] is None:
                finding[key] = default

        # Assign CVSS score if missing or zero
        if not finding.get('cvss_score'):
            finding = self.assign_cvss(finding)

        # Validation flag: finding must have a real location and description
        has_location = bool(
            str(finding['location']).strip() and finding['location'] != 'N/A'
        )
        has_description = bool(
            str(finding['description']).strip()
            and len(str(finding['description'])) > 10
        )
        finding['validated'] = has_location and has_description

        return finding

    def assign_cvss(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assign CVSS v3.1 base score and vector string to a finding based on its
        reported severity. Uses representative default vectors per severity band.

        If the finding already has a non-zero cvss_score, this is a no-op.
        """
        severity = str(finding.get('severity', 'info')).lower().strip()
        if severity not in _CVSS_DEFAULTS:
            severity = 'info'

        score, vector = _CVSS_DEFAULTS[severity]

        # Honour pre-existing AI-assigned scores
        if not finding.get('cvss_score'):
            finding['cvss_score'] = score
        if not finding.get('cvss_vector'):
            finding['cvss_vector'] = vector

        return finding

    def deduplicate(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate findings using a SHA-256 fingerprint of
        (title + location + payload). Maintains original order of first occurrence.
        """
        seen: Set[str] = set()
        unique: List[Dict[str, Any]] = []

        for f in findings:
            title    = str(f.get('title',    '')).lower().strip()
            location = str(f.get('location', '')).strip()
            payload  = str(f.get('payload',  '')).strip()

            fingerprint_data = f"{title}|{location}|{payload}"
            fp = hashlib.sha256(fingerprint_data.encode('utf-8')).hexdigest()

            if fp not in seen:
                seen.add(fp)
                unique.append(f)
            else:
                self.logger.debug(f"Duplicate finding skipped: {title} @ {location}")

        removed = len(findings) - len(unique)
        if removed:
            self.logger.info(f"Deduplication removed {removed} duplicate finding(s).")

        return unique
