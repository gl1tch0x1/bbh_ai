import logging
import hashlib


class Validator:
    """Validates and deduplicates security findings."""

    # Severities that should pass CI gate
    CRITICAL_SEVERITIES = {'critical', 'high'}
    VALID_SEVERITIES = {'critical', 'high', 'medium', 'low', 'info'}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def validate(self, finding: dict, tool_registry=None) -> dict:
        """
        Validate a finding dict:
        - Normalise severity to lowercase
        - Ensure all required keys are present
        - Mark invalid-severity findings as 'info'
        """
        title = finding.get('title', 'Unknown')
        self.logger.info(f"Validating finding: {title}")

        # Normalise severity
        severity = finding.get('severity', 'info').lower().strip()
        if severity not in self.VALID_SEVERITIES:
            self.logger.warning(
                f"Finding '{title}' has unrecognised severity '{severity}' — defaulting to 'info'."
            )
            severity = 'info'
        finding['severity'] = severity

        # Ensure required keys exist with safe defaults
        finding.setdefault('location', '')
        finding.setdefault('description', '')
        finding.setdefault('payload', '')
        finding.setdefault('poc_lang', '')
        finding.setdefault('poc', '')

        # A finding is "validated" when it has a non-empty location and description
        has_location = bool(finding.get('location', '').strip())
        has_description = bool(finding.get('description', '').strip())
        finding['validated'] = has_location and has_description

        if not finding['validated']:
            self.logger.warning(
                f"Finding '{title}' lacks location or description — marked unvalidated."
            )

        return finding

    def deduplicate(self, findings: list) -> list:
        """
        Remove duplicate findings using a SHA-256 fingerprint of
        (title + location + payload). Preserves insertion order.
        """
        seen = set()
        unique = []

        for f in findings:
            title = (f.get('title') or '').lower()
            location = (f.get('location') or '')
            payload = (f.get('payload') or '')
            fingerprint_data = f"{title}:{location}:{payload}"
            fp = hashlib.sha256(fingerprint_data.encode('utf-8')).hexdigest()

            if fp not in seen:
                seen.add(fp)
                unique.append(f)
            else:
                self.logger.debug(f"Duplicate finding skipped: {f.get('title')}")

        removed = len(findings) - len(unique)
        if removed:
            self.logger.info(f"Deduplication removed {removed} duplicate finding(s).")

        return unique