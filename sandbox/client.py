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

    def __init__(self, config: Dict[str, Any], base_workspace: Optional[Path] = None):
        self.config = config
        self.enabled: bool = config.get('sandbox', {}).get('enabled', True)
        self.client: Optional['DockerClient'] = None
        self.container: Optional['Container'] = None
        self.api_url: Optional[str] = None
        self.logger = logging.getLogger(__name__)
        # workspace path on the host (optional) to mount into container
        self.base_workspace = str(base_workspace) if base_workspace else None
        
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
        image = sandbox_cfg['image']
        try:
            # ensure the image exists locally (pull if necessary)
            try:
                self.client.images.get(image)
                self.logger.debug(f"Sandbox image '{image}' already present")
            except Exception:
                self.logger.info(f"Pulling sandbox image '{image}'...")
                self.client.images.pull(image)

            mem_limit = sandbox_cfg.get('memory_limit', '1g')
            cpu_limit = float(sandbox_cfg.get('cpu_limit', 1.0))
            
            volume_map = None
            # priority: explicit config.host_workspace > base_workspace
            host_ws = sandbox_cfg.get('host_workspace') or self.base_workspace
            if host_ws:
                volume_map = {host_ws: {'bind': '/tmp/bbh_workspace', 'mode': 'rw'}}

            self.container = self.client.containers.run(
                image,
                detach=True,
                network=sandbox_cfg.get('network', 'none'),
                mem_limit=mem_limit,
                nano_cpus=int(cpu_limit * 1e9),
                remove=sandbox_cfg.get('ephemeral', True),
                labels={"app": "bbh-ai-sandbox"},
                volumes=volume_map
            )
            self.container.reload()
            
            # Fetch IP with retries
            ip = ""
            for _ in range(15):
                self.container.reload()
                networks = self.container.attrs['NetworkSettings']['Networks']
                if networks:
                    ip = list(networks.values())[0].get('IPAddress', '')
                if ip:
                    break
                time.sleep(0.5)

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
        """Synchronous health check for initial block.

        Retries until the FastAPI server responds with 200 or raises an error
        once the retry limit is exceeded.  Provides detailed logging.
        """
        with httpx.Client() as client:
            for attempt in range(1, self.HEALTH_CHECK_RETRIES + 1):
                try:
                    resp = client.get(f"{self.api_url}/health", timeout=2)
                    if resp.status_code == 200:
                        self.logger.info("Sandbox health check passed.")
                        return
                    else:
                        self.logger.debug(f"Health endpoint returned {resp.status_code}")
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    self.logger.debug(f"Health check attempt {attempt} failed: {e}")
                except Exception as e:
                    self.logger.error(f"Unexpected error during health check: {e}")
                time.sleep(self.HEALTH_CHECK_INTERVAL)
        raise RuntimeError(f"Sandbox at {self.api_url} did not become healthy after {self.HEALTH_CHECK_RETRIES} attempts.")

    async def initialize_async(self) -> None:
        """Initialize the async HTTP client. Should be called within an async context."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=timeout_cfg if (timeout_cfg := self.config.get('scan', {}).get('timeout', 30)) else 30)

    async def execute(self, tool_name: str, args: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
        """Asynchronously execute a tool in the sandbox.

        The `workspace` parameter specifies a directory (on the host) that should
        be made available inside the container for the tool to store temporary
        output. It is mapped into the container when the sandbox is started.  If
        no workspace is provided, we default to an ephemeral folder inside the
        container (typically `/tmp/workspace`).
        """
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
            payload: Dict[str, Any] = {"tool": tool_name, "args": args}
            if workspace:
                payload["workspace"] = str(workspace)

            response = await self._async_client.post(
                f"{self.api_url}/execute",
                json=payload,
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
