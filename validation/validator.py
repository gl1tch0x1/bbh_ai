from typing import Any, Dict, List, Set, Optional, TYPE_CHECKING
import logging
import hashlib

if TYPE_CHECKING:
    from tools.registry import ToolRegistry


class Validator:
    """Validates and deduplicates security findings."""

    # Severities that should pass CI gate
    CRITICAL_SEVERITIES: Set[str] = {'critical', 'high'}
    VALID_SEVERITIES: Set[str] = {'critical', 'high', 'medium', 'low', 'info'}

    def __init__(self, config: Dict[str, Any], workspace: Any, telemetry: Any):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def validate(self, finding: Dict[str, Any], tool_registry: Optional['ToolRegistry'] = None) -> Dict[str, Any]:
        """
        Validate and normalize a finding:
        - Normalise severity to lowercase.
        - Ensure all required keys are present with safe defaults.
        - Mark invalid-severity findings as 'info'.
        - Set a validation flag based on data completeness.
        """
        title = finding.get('title', 'Unknown')
        self.logger.info(f"Validating finding: {title}")

        # Normalise severity
        severity = str(finding.get('severity', 'info')).lower().strip()
        if severity not in self.VALID_SEVERITIES:
            self.logger.warning(
                f"Finding '{title}' has unrecognized severity '{severity}' — defaulting to 'info'."
            )
            severity = 'info'
        finding['severity'] = severity

        # Ensure required keys exist with safe defaults
        # We ensure a flattened structure for consistency
        required_keys = {
            'location': 'N/A',
            'description': 'No description provided.',
            'payload': '',
            'poc_lang': '',
            'poc': '',
            'title': 'Unknown Finding'
        }
        for key, default in required_keys.items():
            if key not in finding or finding[key] is None:
                finding[key] = default

        # A finding is considered "validated" if it has essential context
        has_location = bool(str(finding['location']).strip() and finding['location'] != 'N/A')
        has_description = bool(str(finding['description']).strip() and len(str(finding['description'])) > 10)
        finding['validated'] = has_location and has_description

        return finding

    def deduplicate(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate findings using a SHA-256 fingerprint of (title + location + payload).
        Maintains the original order of first occurrence.
        """
        seen: Set[str] = set()
        unique: List[Dict[str, Any]] = []

        for f in findings:
            # Deterministic fingerprinting
            title = str(f.get('title', '')).lower().strip()
            location = str(f.get('location', '')).strip()
            payload = str(f.get('payload', '')).strip()
            
            fingerprint_data = f"{title}|{location}|{payload}"
            fp = hashlib.sha256(fingerprint_data.encode('utf-8')).hexdigest()

            if fp not in seen:
                seen.add(fp)
                unique.append(f)
            else:
                self.logger.debug(f"Duplicate finding skipped: {title} at {location}")

        removed = len(findings) - len(unique)
        if removed:
            self.logger.info(f"Deduplication removed {removed} duplicate finding(s).")

        return unique
