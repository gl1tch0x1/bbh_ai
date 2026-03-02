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
        self.session = requests.Session()  # Use session for connection pooling
        self.logger = logging.getLogger(__name__)

        if self.enabled:
            try:
                self.client = docker.from_env()
                self._start_container()
            except Exception as e:
                self.logger.error(f"Failed to connect to Docker or start container: {e}")
                # Don't raise here if we want to allow fallback to non-sandboxed mode, 
                # but currently we raise in __init__ as per original design.
                raise

    def _start_container(self):
        sandbox_cfg = self.config['sandbox']
        try:
            # Resource limits to prevent system crashes (especially in VMs)
            mem_limit = sandbox_cfg.get('memory_limit', '1g')
            cpu_limit = float(sandbox_cfg.get('cpu_limit', 1.0))
            
            self.container = self.client.containers.run(
                sandbox_cfg['image'],
                detach=True,
                network=sandbox_cfg.get('network', 'none'),
                mem_limit=mem_limit,
                nano_cpus=int(cpu_limit * 1e9),
                remove=sandbox_cfg.get('ephemeral', True),
                labels={"app": "bbh-ai-sandbox"}
            )
            self.container.reload()
            
            # Fetch IP with a small retry if not immediately available
            ip = ""
            for _ in range(5):
                ip = self.container.attrs['NetworkSettings']['IPAddress']
                if not ip:
                    networks = self.container.attrs['NetworkSettings']['Networks']
                    if networks:
                        ip = list(networks.values())[0].get('IPAddress', '')
                if ip: break
                time.sleep(0.5)
                self.container.reload()

            if not ip:
                raise RuntimeError("Could not determine sandbox container IP address.")

            self.api_url = f"http://{ip}:8000"
            self.logger.info(f"Sandbox container started (Limits: {cpu_limit} CPU, {mem_limit} RAM).")
            self._wait_for_health()

        except Exception:
            self.logger.exception("Failed to start sandbox container.")
            if self.container:
                self._stop_container()
            raise

    def _wait_for_health(self):
        """Poll /health until the sandbox server is ready."""
        for attempt in range(self.HEALTH_CHECK_RETRIES):
            try:
                resp = self.session.get(f"{self.api_url}/health", timeout=2)
                if resp.status_code == 200:
                    self.logger.info("Sandbox health check passed.")
                    return
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(self.HEALTH_CHECK_INTERVAL)

        raise RuntimeError(f"Sandbox at {self.api_url} did not become healthy.")

    def _stop_container(self):
        if self.container:
            try:
                # Use a small timeout for faster exit
                self.container.stop(timeout=5)
                self.logger.info("Sandbox container stopped.")
            except Exception as e:
                self.logger.warning(f"Error stopping sandbox container: {e}")
            finally:
                self.container = None

    def execute(self, tool_name: str, args: dict, workspace=None):
        """Execute a tool via sandbox API or direct call."""
        if self.enabled:
            try:
                timeout = self.config.get('scan', {}).get('timeout', 30)
                response = self.session.post(
                    f"{self.api_url}/execute",
                    json={"tool": tool_name, "args": args},
                    timeout=timeout + 5, # extra margin
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                self.logger.error(f"Sandbox execute failed for '{tool_name}': {e}")
                return {"error": str(e)}
        else:
            from tools.registry import ToolRegistry
            registry = ToolRegistry(self.config, workspace, None)
            tool = registry.get_tool(tool_name)
            if not tool:
                return {"error": f"Tool '{tool_name}' not found."}
            return tool.run(**args)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_container()
        if self.session:
            self.session.close()
        return False
