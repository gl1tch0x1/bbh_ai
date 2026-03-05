import asyncio
import logging
import time
from typing import Any, Dict, Callable, Optional


class AutoHealer:
    """
    AI-powered self-healing system for BBH-AI.
    Automatically retries failed operations and adapts strategies.
    Supports both synchronous (heal_operation) and asynchronous (heal) entry points.
    """

    def __init__(self, config: Dict[str, Any], agent_controller: Any):
        self.config = config
        self.agent_controller = agent_controller
        self.logger = logging.getLogger(__name__)
        self.max_retries: int = config.get('auto_healer', {}).get('max_retries', 3)
        self.retry_delay: float = float(
            config.get('auto_healer', {}).get('retry_delay', 5)
        )

    # ── Async entry point (called by Orchestrator) ─────────────────────────────
    async def heal(self, error: Exception, context: Dict[str, Any]) -> bool:
        """
        Async entry point called by Orchestrator after a phase failure.

        Attempts to re-run the failed phase with exponential back-off up to
        `max_retries` times.  Returns True if recovery succeeded, False otherwise.
        """
        phase_name: str = context.get('phase', 'unknown')
        self.logger.info(
            f"[AutoHealer] Initiating recovery for phase '{phase_name}' "
            f"after error: {error}"
        )

        for attempt in range(1, self.max_retries + 1):
            delay = self.retry_delay * (2 ** (attempt - 1))  # exponential back-off
            self.logger.info(
                f"[AutoHealer] Healing attempt {attempt}/{self.max_retries} "
                f"for '{phase_name}' (waiting {delay:.1f}s)..."
            )
            await asyncio.sleep(delay)
            try:
                result = await asyncio.to_thread(
                    self.agent_controller.run_phase, phase_name, context
                )
                self.logger.info(
                    f"[AutoHealer] Phase '{phase_name}' recovered on attempt {attempt}."
                )
                return bool(result)
            except Exception as exc:
                self.logger.warning(
                    f"[AutoHealer] Recovery attempt {attempt} failed: {exc}"
                )

        self.logger.error(
            f"[AutoHealer] All {self.max_retries} recovery attempts exhausted "
            f"for phase '{phase_name}'."
        )
        return False

    # ── Synchronous helpers ────────────────────────────────────────────────────
    def heal_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute a synchronous operation with automatic retry and linear back-off."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                self.logger.warning(
                    f"[AutoHealer] Operation failed "
                    f"(attempt {attempt}/{self.max_retries}): {exc}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
        raise last_exc  # type: ignore[misc]

    def heal_phase(self, phase_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronously heal a failed phase by re-running with adapted context."""
        self.logger.info(
            f"[AutoHealer] Attempting synchronous heal for phase: {phase_name}"
        )
        return self.agent_controller.run_phase(phase_name, context)