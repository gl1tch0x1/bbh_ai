import logging
import time
from typing import Any, Dict, Callable, Optional

class AutoHealer:
    """
    AI-powered self-healing system for BBH-AI.
    Automatically retries failed operations and adapts strategies.
    """
    def __init__(self, config: Dict[str, Any], agent_controller: Any):
        self.config = config
        self.agent_controller = agent_controller
        self.logger = logging.getLogger(__name__)
        self.max_retries = config.get('auto_healer', {}).get('max_retries', 3)
        self.retry_delay = config.get('auto_healer', {}).get('retry_delay', 5)

    def heal_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with automatic retry and healing."""
        for attempt in range(self.max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                self.logger.warning(f"Operation failed (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    # Could add AI-based healing logic here
                else:
                    raise

    def heal_phase(self, phase_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Heal a failed phase by re-running with adapted context."""
        self.logger.info(f"Attempting to heal phase: {phase_name}")
        # Use agent_controller to re-run phase with modified context
        return self.agent_controller.run_phase(phase_name, context)