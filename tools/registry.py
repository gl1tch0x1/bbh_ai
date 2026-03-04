from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING
import importlib
import logging
from pathlib import Path
from functools import lru_cache

if TYPE_CHECKING:
    from telemetry.logger import Telemetry


class ToolRegistry:
    """
    Dynamically indexes and lazy-loads tool wrappers from tools/wrappers/.
    Improves startup speed by only instantiating tools when actually requested.
    Implements category-level caching for O(1) lookups.
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
        # Cache for category lookups: category -> [tool_names]
        self._category_cache: Dict[str, List[str]] = {}
        self._category_cache_built = False
        
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
            
            # 🔗 Inject Sandbox Client for Industrial Execution Bridge
            # Avoid circular import by using instance check or duck typing
            if hasattr(instance, 'sandbox'):
                # Fetch sandbox from config or orchestrator context (passed via config if needed)
                # In our Orchestrator, we should ideally pass a sandbox object.
                # Since config is shared, we can also use a singleton or global if needed,
                # but passing it via property is cleaner.
                instance.sandbox = self.config.get('_sandbox_client')
                
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
        Loads instances on-demand. Uses category caching for O(1) lookups.
        Falls back to empty list if no tools found for category.
        """
        # If category is '*', we must load everything (rarely used by agents)
        if category == '*':
            for name in self._tool_index:
                self._load_instance(name)
            return list(self._instances.values())

        # Build category cache once (lazy initialization)
        if not self._category_cache_built:
            self._build_category_cache()
            self._category_cache_built = True
        
        # O(1) lookup: get tool names by category, then load instances
        tool_names = self._category_cache.get(category, [])
        
        matched_instances = []
        for name in tool_names:
            instance = self._load_instance(name)
            if instance:
                matched_instances.append(instance)

        if not matched_instances:
            # Log warning but return empty list (agents can handle empty tool lists)
            self.logger.warning(f"No tools found for category '{category}'.")
        
        return matched_instances

    def _build_category_cache(self) -> None:
        """Build a cache mapping categories to tool names for fast lookups."""
        for name in self._tool_index:
            try:
                instance = self._load_instance(name)
                if instance:
                    tool_categories = getattr(instance, 'categories', [])
                    for cat in tool_categories:
                        if cat not in self._category_cache:
                            self._category_cache[cat] = []
                        self._category_cache[cat].append(name)
            except Exception as e:
                self.logger.debug(f"Skipped category caching for {name}: {e}")

    def list_tools(self) -> List[str]:
        """Return sorted list of all indexed tool names."""
        return sorted(self._tool_index.keys())
