import importlib
import logging
from pathlib import Path

class ToolRegistry:
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self.tools = {}
        self._load_tools()

    def _load_tools(self):
        wrappers_dir = Path(__file__).parent / "wrappers"
        for pyfile in wrappers_dir.glob("*.py"):
            if pyfile.name.startswith("__"):
                continue
            module_name = pyfile.stem
            class_name = module_name.title().replace('_', '') + "Tool"
            try:
                module = importlib.import_module(f"tools.wrappers.{module_name}")
                tool_class = getattr(module, class_name)
                instance = tool_class(self.config, self.workspace, self.telemetry)
                self.tools[module_name] = instance
                self.logger.debug(f"Loaded tool: {module_name}")
            except Exception as e:
                self.logger.error(f"Failed to load tool {module_name}: {e}")

    def get_tool(self, name):
        return self.tools.get(name)

    def get_tools(self, category):
        # For now, return all tools; can be filtered by category later
        return list(self.tools.values())