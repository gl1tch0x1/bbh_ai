import time
import logging
import requests
import docker

logger_global = logging.getLogger(__name__)


class SandboxClient:
    """
    Manages a Docker sandbox container for isolated tool execution.
    Supports context manager usage for reliable cleanup.
    """

    HEALTH_CHECK_RETRIES = 15
    HEALTH_CHECK_INTERVAL = 1.0   # seconds between retries

    def __init__(self, config):
        self.config = config
        self.enabled = config['sandbox']['enabled']
        self.client = None
        self.container = None
        self.api_url = None
        self.logger = logging.getLogger(__name__)

        if self.enabled:
            try:
                self.client = docker.from_env()
            except Exception as e:
                self.logger.error(f"Failed to connect to Docker: {e}")
                raise
            self._start_container()

    def _start_container(self):
        sandbox_cfg = self.config['sandbox']
        try:
            self.container = self.client.containers.run(
                sandbox_cfg['image'],
                detach=True,
                network=sandbox_cfg.get('network', 'none'),
                mem_limit=sandbox_cfg.get('memory_limit'),
                nano_cpus=int(sandbox_cfg.get('cpu_limit', 1) * 1e9),
                remove=sandbox_cfg.get('ephemeral', True),
            )
            self.container.reload()
            ip = self.container.attrs['NetworkSettings']['IPAddress']
            if not ip:
                networks = self.container.attrs['NetworkSettings']['Networks']
                if networks:
                    ip = list(networks.values())[0].get('IPAddress', '')

            if not ip:
                raise RuntimeError("Could not determine sandbox container IP address.")

            self.api_url = f"http://{ip}:8000"
            self.logger.info(f"Sandbox container started. Waiting for health check at {self.api_url}…")
            self._wait_for_health()

        except Exception:
            self.logger.exception("Failed to start sandbox container.")
            raise

    def _wait_for_health(self):
        """Poll /health until the sandbox server is ready (replaces fragile sleep(2))."""
        for attempt in range(self.HEALTH_CHECK_RETRIES):
            try:
                resp = requests.get(f"{self.api_url}/health", timeout=2)
                if resp.status_code == 200:
                    self.logger.info("Sandbox health check passed.")
                    return
            except requests.ConnectionError:
                pass
            self.logger.debug(f"Health check attempt {attempt + 1}/{self.HEALTH_CHECK_RETRIES}…")
            time.sleep(self.HEALTH_CHECK_INTERVAL)

        raise RuntimeError(
            f"Sandbox at {self.api_url} did not become healthy after "
            f"{self.HEALTH_CHECK_RETRIES} attempts."
        )

    def _stop_container(self):
        if self.container:
            try:
                self.container.stop()
                self.logger.info("Sandbox container stopped.")
            except Exception as e:
                self.logger.warning(f"Error stopping sandbox container: {e}")
            finally:
                self.container = None

    def execute(self, tool_name: str, args: dict, workspace=None):
        """
        Execute a tool. Uses sandbox HTTP API when enabled;
        falls back to direct ToolRegistry call with the provided workspace.
        """
        if self.enabled:
            try:
                response = requests.post(
                    f"{self.api_url}/execute",
                    json={"tool": tool_name, "args": args},
                    timeout=self.config.get('scan', {}).get('timeout', 30),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                self.logger.error(f"Sandbox execute failed for '{tool_name}': {e}")
                return {"error": str(e)}
        else:
            # Direct execution — workspace must be provided to avoid NoneType crashes
            from tools.registry import ToolRegistry
            registry = ToolRegistry(self.config, workspace, None)
            tool = registry.get_tool(tool_name)
            if not tool:
                return {"error": f"Tool '{tool_name}' not found in registry."}
            return tool.run(**args)

    # ── Context manager support (replaces unreliable __del__) ────────────────
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_container()
        return False   # Do not suppress exceptions