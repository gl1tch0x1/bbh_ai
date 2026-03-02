import logging
import re
import warnings
from urllib.parse import urljoin

import requests
import urllib3


class JsParserTool:
    name = "js_parser"
    categories = ["recon"]
    input_schema = {"js_url": str, "base_url": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 15)

    def run(self, js_url: str, base_url: str = None) -> dict:
        self.logger.info(f"Parsing JS from {js_url}")
        # Suppress the InsecureRequestWarning but log it clearly once
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.logger.debug("SSL verification disabled for JS fetch — do not use on untrusted networks.")
        try:
            response = requests.get(js_url, timeout=self._timeout, verify=False)
            if response.status_code != 200:
                self.logger.warning(f"JS fetch returned HTTP {response.status_code} for {js_url}")
                return {"error": f"HTTP {response.status_code}", "endpoints": []}

            content = response.text
            # Extract relative paths and absolute URLs
            raw_matches = re.findall(
                r'(?:"|\'|`)((https?://[^\s"\'`<>]+)|(/[^\s"\'`<>]{2,}))',
                content
            )
            endpoints: set = set()
            for full, absolute, relative in raw_matches:
                if absolute:
                    endpoints.add(absolute)
                elif relative and base_url:
                    resolved = urljoin(base_url, relative)
                    endpoints.add(resolved)
                elif relative:
                    endpoints.add(relative)

            if self.telemetry:
                self.telemetry.log_tool_call("js_parser", {"js_url": js_url}, len(endpoints))
            self.logger.info(f"js_parser extracted {len(endpoints)} endpoints from {js_url}")
            return {"js_url": js_url, "endpoints": list(endpoints)}

        except requests.Timeout:
            self.logger.error(f"js_parser timed out fetching {js_url}")
            return {"error": "timeout", "endpoints": []}
        except Exception as e:
            self.logger.exception(f"JS parsing failed for {js_url}")
            return {"error": str(e), "endpoints": []}