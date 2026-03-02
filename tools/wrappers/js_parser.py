import requests
import re
import logging
from urllib.parse import urljoin

class JsParserTool:
    name = "js_parser"
    input_schema = {"js_url": str, "base_url": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)

    def run(self, js_url, base_url=None):
        self.logger.info(f"Parsing JS from {js_url}")
        try:
            response = requests.get(js_url, timeout=10, verify=False)
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}", "endpoints": []}
            content = response.text
            # Extract potential URLs/endpoints
            urls = re.findall(r'(https?://[^\s"\'<>]+|/[^\s"\'<>]+)', content)
            endpoints = set()
            for u in urls:
                if u.startswith('/') and base_url:
                    u = urljoin(base_url, u)
                if u.startswith(('http://', 'https://')):
                    endpoints.add(u)
                elif u.startswith('/'):
                    endpoints.add(u)
            self.telemetry.log_tool_call("js_parser", {"js_url": js_url}, len(endpoints))
            return {"js_url": js_url, "endpoints": list(endpoints)}
        except Exception as e:
            self.logger.exception(f"JS parsing failed for {js_url}")
            return {"error": str(e), "endpoints": []}