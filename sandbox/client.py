import requests
import docker
import logging
import time

class SandboxClient:
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
        sandbox_config = self.config['sandbox']
        try:
            self.container = self.client.containers.run(
                sandbox_config['image'],
                detach=True,
                network=sandbox_config.get('network', 'none'),
                mem_limit=sandbox_config.get('memory_limit'),
                nano_cpus=int(sandbox_config.get('cpu_limit', 1) * 1e9),
                remove=sandbox_config.get('ephemeral', True)
            )
            time.sleep(2)
            self.container.reload()
            ip = self.container.attrs['NetworkSettings']['IPAddress']
            if not ip and sandbox_config.get('network') == 'bridge':
                networks = self.container.attrs['NetworkSettings']['Networks']
                if networks:
                    ip = list(networks.values())[0].get('IPAddress')
            if not ip:
                self.logger.error("Could not determine sandbox container IP")
                raise RuntimeError("Sandbox IP not found")
            self.api_url = f"http://{ip}:8000"
            self.logger.info(f"Sandbox container started at {self.api_url}")
        except Exception as e:
            self.logger.exception("Failed to start sandbox container")
            raise

    def _stop_container(self):
        if self.container:
            try:
                self.container.stop()
                self.logger.info("Sandbox container stopped")
            except Exception as e:
                self.logger.warning(f"Error stopping container: {e}")

    def execute(self, tool_name, args):
        if not self.enabled:
            from tools.registry import ToolRegistry
            registry = ToolRegistry(self.config, None, None)
            tool = registry.get_tool(tool_name)
            return tool.run(**args)
        else:
            try:
                response = requests.post(f"{self.api_url}/execute", json={
                    "tool": tool_name,
                    "args": args
                }, timeout=30)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                self.logger.error(f"Sandbox execute failed: {e}")
                return {"error": str(e)}

    def __del__(self):
        self._stop_container()