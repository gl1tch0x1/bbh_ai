import json
import csv
from pathlib import Path
from jinja2 import Template
from datetime import datetime
import logging


class ReportGenerator:
    def __init__(self, config, workspace):
        self.config = config
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def generate(self, findings):
        report_paths = {}

        formats = self.config.get("reporting", {}).get("formats", [])

        if "markdown" in formats:
            report_paths["markdown"] = self._generate_markdown(findings)

        if "json" in formats:
            report_paths["json"] = self._generate_json(findings)

        if "csv" in formats:
            report_paths["csv"] = self._generate_csv(findings)

        return report_paths

    def _generate_markdown(self, findings):
        template_str = """
# Security Scan Report
**Date:** {{ date }}
**Target:** {{ target }}

## Summary
- Total vulnerabilities: {{ findings|length }}
- Critical: {{ critical_count }}
- High: {{ high_count }}
- Medium: {{ medium_count }}
- Low: {{ low_count }}

## Details
{% for f in findings %}
### {{ f.title }}
- **Severity:** {{ f.severity }}
- **Location:** {{ f.location }}
- **Description:** {{ f.description }}
- **PoC:**
```{{ f.poc_lang }}
{{ f.poc }}
```
{% endfor %}
"""

        template = Template(template_str)

        critical_count = sum(
            1 for f in findings if f.get("severity", "").lower() == "critical"
        )
        high_count = sum(
            1 for f in findings if f.get("severity", "").lower() == "high"
        )
        medium_count = sum(
            1 for f in findings if f.get("severity", "").lower() == "medium"
        )
        low_count = sum(
            1 for f in findings if f.get("severity", "").lower() == "low"
        )

        output = template.render(
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            target=self.config.get("target", "Unknown"),
            findings=findings,
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
        )

        report_path = self.workspace / "report.md"
        report_path.write_text(output, encoding="utf-8")

        self.logger.info(f"Markdown report generated at {report_path}")
        return str(report_path)

    def _generate_json(self, findings):
        report_data = {
            "date": datetime.now().isoformat(),
            "target": self.config.get("target", "Unknown"),
            "total_findings": len(findings),
            "findings": findings,
        }

        report_path = self.workspace / "report.json"

        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)

        self.logger.info(f"JSON report generated at {report_path}")
        return str(report_path)

    def _generate_csv(self, findings):
        report_path = self.workspace / "report.csv"

        fieldnames = ["title", "severity", "location", "description", "poc_lang", "poc"]

        with report_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for finding in findings:
                writer.writerow({
                    "title": finding.get("title", ""),
                    "severity": finding.get("severity", ""),
                    "location": finding.get("location", ""),
                    "description": finding.get("description", ""),
                    "poc_lang": finding.get("poc_lang", ""),
                    "poc": finding.get("poc", ""),
                })

        self.logger.info(f"CSV report generated at {report_path}")
        return str(report_path)
