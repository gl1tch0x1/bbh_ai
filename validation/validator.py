import logging
import hashlib


class Validator:
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def validate(self, finding, tool_registry):
        self.logger.info(f"Validating finding: {finding.get('title', 'Unknown')}")

        # Placeholder for real validation logic
        finding["validated"] = True
        return finding

    def deduplicate(self, findings):
        seen = set()
        unique = []

        for f in findings:
            location = f.get("location") or ""
            payload = f.get("payload") or ""
            fingerprint_data = f"{location}:{payload}"

            fp = hashlib.sha256(fingerprint_data.encode()).hexdigest()

            if fp not in seen:
                seen.add(fp)
                unique.append(f)

        return unique