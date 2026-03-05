"""
ci/notifier.py — Sends scan results to Slack and Jira.
Called automatically by Orchestrator after a scan completes.
"""

import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)


class CINotifier:
    """Enterprise-grade CI/CD notifier for BBH-AI."""

    def __init__(self, config: dict):
        self.ci_cfg = config.get('ci', {})
        self.slack_webhook: str = self.ci_cfg.get('slack_webhook', '')
        
        # Jira Config
        self.jira_url: str = self.ci_cfg.get('jira_url', '')
        self.jira_email: str = self.ci_cfg.get('jira_email', '')
        self.jira_token: str = self.ci_cfg.get('jira_token', '')
        self.jira_project: str = self.ci_cfg.get('jira_project_key', '')

    def notify(
        self,
        target: str,
        findings: List[Dict[str, Any]],
        report_path: str,
        exit_code: int,
    ) -> None:
        """Dispatch all configured notification channels."""
        counts = self._count_severities(findings)

        if self.slack_webhook and self.slack_webhook.startswith('https://'):
            self._notify_slack(target, counts, report_path, exit_code)
            
        if self.jira_url and self.jira_token and self.jira_project:
            self._notify_jira(target, findings, report_path)

    @staticmethod
    def _count_severities(findings: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {
            'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0,
        }
        for f in findings:
            sev = str(f.get('severity', 'info')).lower()
            if sev in counts:
                counts[sev] += 1
        counts['total'] = len(findings)
        return counts

    def _notify_slack(
        self, target: str, counts: Dict[str, int], report_path: str, exit_code: int
    ) -> None:
        if not self.slack_webhook:
            return

        try:
            icon = "🔴" if counts['critical'] else "🟠" if counts['high'] else "🟢"
            text = (
                f"{icon} *BBH-AI Scan Complete* — `{target}`\n"
                f"*Findings:* {counts['total']} total "
                f"({counts['critical']} critical, {counts['high']} high)\n"
                f"*Report:* `{report_path}`\n"
                f"*Exit code:* `{exit_code}`"
            )
            body = {"text": text}
            resp = requests.post(self.slack_webhook, json=body, timeout=10)
            resp.raise_for_status()
            logger.info("✓ Slack notification sent")
        except Exception as exc:
            logger.warning(f"Slack notification failed: {exc}")

    def _notify_jira(
        self, target: str, findings: List[Dict[str, Any]], report_path: str
    ) -> None:
        """Create Jira tickets for Critical and High findings."""
        if not all([self.jira_url, self.jira_email, self.jira_token, self.jira_project]):
            return

        critical_high = [
            f for f in findings 
            if str(f.get('severity', '')).lower() in ('critical', 'high')
        ]
        
        if not critical_high:
            logger.info("No critical/high findings to report to Jira.")
            return

        logger.info(f"Opening {len(critical_high)} Jira issues...")
        auth = (self.jira_email, self.jira_token)
        headers = {"Accept": "application/json"}
        url = f"{self.jira_url.rstrip('/')}/rest/api/2/issue"

        for finding in critical_high:
            try:
                title = f"[BBH-AI] {finding.get('title')} on {target}"
                desc = (
                    f"*Target:* {target}\n"
                    f"*Severity:* {finding.get('severity').upper()}\n"
                    f"*CVSS:* {finding.get('cvss_score')} ({finding.get('cvss_vector')})\n\n"
                    f"*Location:*\n{finding.get('location')}\n\n"
                    f"*Description:*\n{finding.get('description')}\n\n"
                    f"*Root Cause:*\n{finding.get('root_cause')}\n\n"
                    f"*Report Path:*\n{report_path}"
                )
                
                payload = {
                    "fields": {
                        "project": {"key": self.jira_project},
                        "summary": title,
                        "description": desc,
                        "issuetype": {"name": "Bug"}
                    }
                }
                
                resp = requests.post(url, json=payload, auth=auth, headers=headers, timeout=15)
                resp.raise_for_status()
                key = resp.json().get('key')
                logger.info(f"✓ Jira issue created: {key}")
                
            except Exception as exc:
                logger.warning(f"Failed to create Jira issue for '{title}': {exc}")
