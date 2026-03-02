import importlib
import logging
from pathlib import Path


class ToolRegistry:
    """
    Dynamically loads all tool wrappers from tools/wrappers/.
    Supports category-based filtering via a 'categories' attribute on each tool class.
    """

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self.tools: dict = {}
        self._load_tools()

    def _load_tools(self):
        wrappers_dir = Path(__file__).parent / "wrappers"
        # Recursively search for all .py files in subdirectories
        for pyfile in sorted(wrappers_dir.rglob("*.py")):
            if pyfile.name.startswith("__") or pyfile.is_dir():
                continue
            
            # Module name is the stem (e.g., "js_parser")
            module_name = pyfile.stem
            # Get the path relative to wrappers_dir and convert to dot notation
            # e.g., "web_analysis/js_parser.py" -> "web_analysis.js_parser"
            relative_parts = pyfile.relative_to(wrappers_dir).with_suffix('').parts
            module_dot_path = ".".join(relative_parts)
            
            # class_name = "JsParserTool"
            class_name = "".join(part.capitalize() for part in module_name.split("_")) + "Tool"
            
            try:
                module = importlib.import_module(f"tools.wrappers.{module_dot_path}")
                tool_class = getattr(module, class_name)
                instance = tool_class(self.config, self.workspace, self.telemetry)
                self.tools[module_name] = instance
                self.logger.debug(f"Loaded tool: {module_name} (class: {class_name} from {module_dot_path})")
            except AttributeError:
                self.logger.error(
                    f"Tool class '{class_name}' not found in tools/wrappers/{module_dot_path.replace('.', '/')}.py"
                )
            except Exception as e:
                self.logger.error(f"Failed to load tool '{module_name}' from '{module_dot_path}': {e}")

    def get_tool(self, name: str):
        """Return a single tool by name, or None if not found."""
        return self.tools.get(name)

    def get_tools(self, category: str) -> list:
        """
        Return tools belonging to a given category.
        Falls back to ALL tools if category is '*' or no tools declare the category.
        Each tool class must declare a 'categories' list attribute.
        """
        if category == '*':
            return list(self.tools.values())

        filtered = [
            t for t in self.tools.values()
            if category in getattr(t, 'categories', [])
        ]

        if not filtered:
            self.logger.warning(
                f"No tools found for category '{category}'. "
                f"Returning all tools as fallback."
            )
            return list(self.tools.values())

        return filtered

    def list_tools(self) -> list[str]:
        """Return sorted list of all loaded tool names."""
        return sorted(self.tools.keys())