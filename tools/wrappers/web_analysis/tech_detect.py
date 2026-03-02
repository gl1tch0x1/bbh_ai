import logging


class TechDetectTool:
    name = "tech_detect"
    categories = ["recon"]
    input_schema = {"url": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        # Lazy-load Wappalyzer — avoids network call at import/registry-load time
        self._wappalyzer = None

    def _get_wappalyzer(self):
        """Initialise Wappalyzer once on first use (lazy singleton)."""
        if self._wappalyzer is None:
            try:
                from Wappalyzer import Wappalyzer
                self._wappalyzer = Wappalyzer.latest()
            except Exception as e:
                self.logger.error(f"Failed to initialise Wappalyzer: {e}")
                raise
        return self._wappalyzer

    def run(self, url: str) -> dict:
        self.logger.info(f"Detecting technologies for {url}")
        try:
            from Wappalyzer import WebPage
            wappalyzer = self._get_wappalyzer()
            webpage = WebPage.new_from_url(url, verify=False)
            technologies = wappalyzer.analyze(webpage)
            tech_list = list(technologies)
            if self.telemetry:
                self.telemetry.log_tool_call("tech_detect", {"url": url}, len(tech_list))
            self.logger.info(f"tech_detect found {len(tech_list)} technologies at {url}")
            return {"url": url, "technologies": tech_list}
        except Exception as e:
            self.logger.exception(f"Tech detection failed for {url}")
            return {"error": str(e), "technologies": []}