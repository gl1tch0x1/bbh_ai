import requests
from Wappalyzer import Wappalyzer, WebPage
import logging

class TechDetectTool:
    name = "tech_detect"
    input_schema = {"url": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self.wappalyzer = Wappalyzer.latest()

    def run(self, url):
        self.logger.info(f"Detecting technology for {url}")
        try:
            webpage = WebPage.new_from_url(url, verify=False)
            technologies = self.wappalyzer.analyze(webpage)
            self.telemetry.log_tool_call("tech_detect", {"url": url}, len(technologies))
            return {"url": url, "technologies": list(technologies)}
        except Exception as e:
            self.logger.exception(f"Tech detection failed for {url}")
            return {"error": str(e), "technologies": []}