from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING
import importlib
import logging
from pathlib import Path

if TYPE_CHECKING:
    from telemetry.logger import Telemetry


class ToolRegistry:
    """
    Dynamically indexes and lazy-loads tool wrappers from tools/wrappers/.
    Improves startup speed by only instantiating tools when actually requested.
    """

    def __init__(self, config: Dict[str, Any], workspace: Path, telemetry: 'Telemetry'):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        
        # Maps tool name to metadata (module_path, class_name)
        self._tool_index: Dict[str, Dict[str, str]] = {}
        # Cache for instantiated tools
        self._instances: Dict[str, Any] = {}
        
        self._index_tools()

    def _index_tools(self) -> None:
        """Scan the wrappers directory and index tool metadata."""
        wrappers_dir = Path(__file__).parent / "wrappers"
        if not wrappers_dir.exists():
            self.logger.error(f"Wrappers directory not found: {wrappers_dir}")
            return

        for pyfile in sorted(wrappers_dir.rglob("*.py")):
            if pyfile.name.startswith("__") or pyfile.is_dir():
                continue
            
            module_name = pyfile.stem
            # Get the path relative to wrappers_dir and convert to dot notation
            try:
                relative_parts = pyfile.relative_to(wrappers_dir).with_suffix('').parts
                module_dot_path = ".".join(relative_parts)
                class_name = "".join(part.capitalize() for part in module_name.split("_")) + "Tool"
                
                self._tool_index[module_name] = {
                    "module": f"tools.wrappers.{module_dot_path}",
                    "class": class_name
                }
            except Exception as e:
                self.logger.error(f"Failed to index tool at {pyfile}: {e}")

    def _load_instance(self, name: str) -> Optional[Any]:
        """Lazy-load and instantiate a tool by name."""
        if name in self._instances:
            return self._instances[name]
        
        if name not in self._tool_index:
            return None
            
        metadata = self._tool_index[name]
        try:
            module = importlib.import_module(metadata["module"])
            tool_class: Type[Any] = getattr(module, metadata["class"])
            instance = tool_class(self.config, self.workspace, self.telemetry)
            self._instances[name] = instance
            return instance
        except Exception as e:
            self.logger.error(f"Failed to lazy-load tool '{name}': {e}")
            return None

    def get_tool(self, name: str) -> Optional[Any]:
        """Return a single tool instance by name, or None if not found."""
        return self._load_instance(name)

    def get_tools(self, category: str) -> List[Any]:
        """
        Return tools belonging to a given category.
        Loads instances on-demand.
        """
        # If category is '*', we must load everything (rarely used by agents)
        if category == '*':
            for name in self._tool_index:
                self._load_instance(name)
            return list(self._instances.values())

        # First, ensure all potential tools for this category are indexed
        # (Though we already indexed all names in __init__)
        
        # We need to peek at 'categories' attribute without full instantiation 
        # for ALL tools, or just instantiate them all. 
        # Optimization: Instantiate all tools for the requested category.
        
        matched_instances = []
        for name in self._tool_index:
            instance = self._load_instance(name)
            if instance and category in getattr(instance, 'categories', []):
                matched_instances.append(instance)

        if not matched_instances and category != 'vuln':
            # Note: Category 'vuln' is usually specific, others might fallback
            self.logger.warning(f"No tools found for category '{category}'. Falling back to all loaded.")
            return list(self._instances.values())

        return matched_instances

    def list_tools(self) -> List[str]:
        """Return sorted list of all indexed tool names."""
        return sorted(self._tool_index.keys())
