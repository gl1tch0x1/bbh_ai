from typing import Any, Dict, Optional, Union, TYPE_CHECKING
import time
import asyncio
import logging
import httpx
import docker
from pathlib import Path

if TYPE_CHECKING:
    from docker.models.containers import Container
    from docker import DockerClient


class SandboxClient:
    """
    Manages a Docker sandbox container for isolated tool execution.
    Refactored for async execution to support high-performance orchestration.
    """

    HEALTH_CHECK_RETRIES = 15
    HEALTH_CHECK_INTERVAL = 1.0  # seconds

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled: bool = config['sandbox'].get('enabled', True)
        self.client: Optional['DockerClient'] = None
        self.container: Optional['Container'] = None
        self.api_url: Optional[str] = None
        self.logger = logging.getLogger(__name__)
        
        # Async HTTP client for tool execution
        self._async_client: Optional[httpx.AsyncClient] = None

        if self.enabled:
            try:
                self.client = docker.from_env()
                self._start_container()
            except Exception as e:
                self.logger.error(f"Failed to connect to Docker or start container: {e}")
                raise

    def _start_container(self) -> None:
        """Synchronous initialization of the Docker container."""
        sandbox_cfg = self.config['sandbox']
        try:
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
            
            # Fetch IP
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
            self.logger.info(f"Sandbox container started at {self.api_url} ({cpu_limit} CPU, {mem_limit} RAM).")
            
            # We must run health check synchronously here or during first async entry
            # For simplicity, we'll do a blocking health check during init
            self._wait_for_health_sync()

        except Exception:
            self.logger.exception("Failed to start sandbox container.")
            if self.container:
                self._stop_container()
            raise

    def _wait_for_health_sync(self) -> None:
        """Synchronous health check for initial block."""
        with httpx.Client() as client:
            for attempt in range(self.HEALTH_CHECK_RETRIES):
                try:
                    resp = client.get(f"{self.api_url}/health", timeout=2)
                    if resp.status_code == 200:
                        self.logger.info("Sandbox health check passed.")
                        return
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass
                time.sleep(self.HEALTH_CHECK_INTERVAL)
        raise RuntimeError(f"Sandbox at {self.api_url} did not become healthy.")

    async def initialize_async(self) -> None:
        """Initialize the async HTTP client. Should be called within an async context."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=timeout_cfg if (timeout_cfg := self.config.get('scan', {}).get('timeout', 30)) else 30)

    async def execute(self, tool_name: str, args: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
        """Asynchronously execute a tool in the sandbox."""
        if not self.enabled:
            # Fallback to local execution (sync wrap)
            from tools.registry import ToolRegistry
            registry = ToolRegistry(self.config, workspace, None) # type: ignore
            tool = registry.get_tool(tool_name)
            if not tool:
                return {"error": f"Tool '{tool_name}' not found locally."}
            return tool.run(**args)

        if self._async_client is None:
            await self.initialize_async()

        try:
            timeout = self.config.get('scan', {}).get('timeout', 30)
            response = await self._async_client.post(
                f"{self.api_url}/execute",
                json={"tool": tool_name, "args": args},
                timeout=timeout + 10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Sandbox async execute failed for '{tool_name}': {e}")
            return {"error": str(e)}

    def _stop_container(self) -> None:
        """Stops the sandbox container."""
        if self.container:
            try:
                self.container.stop(timeout=5)
                self.logger.info("Sandbox container stopped.")
            except Exception as e:
                self.logger.warning(f"Error stopping sandbox container: {e}")
            finally:
                self.container = None

    async def close(self) -> None:
        """Cleanup async resources."""
        if self._async_client:
            await self._async_client.aclose()
        self._stop_container()

    def __enter__(self) -> 'SandboxClient':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop_container()
