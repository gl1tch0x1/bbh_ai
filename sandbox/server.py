"""
sandbox/server.py — FastAPI Sandbox Execution Server

Runs inside the Docker container and exposes REST endpoints for:
  - /execute   Tool wrapper execution (original)
  - /browser   Playwright browser automation
  - /terminal  Shell command execution
  - /proxy     HTTP request intercept/replay
  - /python    Arbitrary Python snippet execution
  - /tools     List available tool wrappers
  - /health    Health check
"""

import importlib.util
import logging
import os
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="BBH-AI Sandbox", version="2.0")
logger = logging.getLogger("sandbox")
logging.basicConfig(level=logging.INFO)

TOOLS_PATH = os.environ.get("TOOLS_PATH", "/app/tools/wrappers")
CONTAINER_WORKSPACE = "/tmp/bbh_workspace"
_MAX_TIMEOUT = 120  # hard cap for all primitive endpoints


# ── Helpers ───────────────────────────────────────────────────────────────────
def _make_workspace(tool_name: str) -> str:
    """Create and return a unique per-invocation workspace directory."""
    workspace_dir = os.path.join(
        CONTAINER_WORKSPACE,
        f"{tool_name}_{int(time.time())}_{uuid.uuid4().hex[:6]}",
    )
    try:
        os.makedirs(workspace_dir, exist_ok=True)
    except Exception as exc:
        logger.warning(f"Could not create workspace dir {workspace_dir}: {exc}")
    return workspace_dir


def _load_tool(tool_name: str):
    """Recursively locate and instantiate a tool wrapper by name."""
    target_file = f"{tool_name}.py"
    module_path = None

    for root, _dirs, files in os.walk(TOOLS_PATH):
        if target_file in files:
            module_path = os.path.join(root, target_file)
            break

    if not module_path or not os.path.exists(module_path):
        return None

    try:
        spec = importlib.util.spec_from_file_location(tool_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.error(f"Failed to import tool '{tool_name}' from {module_path}: {exc}")
        return None

    class_name = (
        "".join(x.title() for x in tool_name.replace("-", "_").split("_")) + "Tool"
    )
    tool_class = getattr(module, class_name, None)
    if tool_class:
        try:
            return tool_class(config={}, workspace=None, telemetry=None)
        except Exception as exc:
            logger.error(f"Error instantiating tool '{tool_name}': {exc}")
            return None
    return None


# ── Request / Response Models ─────────────────────────────────────────────────
class ExecuteRequest(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    workspace: Optional[str] = None


class BrowserRequest(BaseModel):
    action: str  # navigate | click | fill | evaluate | screenshot | get_cookies
    args: Dict[str, Any] = Field(default_factory=dict)
    timeout: int = Field(default=30_000, le=120_000)


class TerminalRequest(BaseModel):
    command: str
    timeout: int = Field(default=30, le=_MAX_TIMEOUT)
    cwd: Optional[str] = None


class ProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    params: Optional[Dict[str, str]] = None
    timeout: int = Field(default=30, le=_MAX_TIMEOUT)
    follow_redirects: bool = False


class PythonRequest(BaseModel):
    script: str
    timeout: int = Field(default=30, le=_MAX_TIMEOUT)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0"}


@app.get("/tools")
def list_tools():
    tool_names: List[str] = []
    for root, _dirs, files in os.walk(TOOLS_PATH):
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                tool_names.append(os.path.splitext(f)[0])
    return {"tools": sorted(tool_names)}


@app.post("/execute")
def execute(req: ExecuteRequest):
    """Execute a tool wrapper by name."""
    logger.info(
        f"Executing tool: {req.tool} with args {req.args} workspace={req.workspace}"
    )
    workspace_dir = _make_workspace(req.tool)

    tool = _load_tool(req.tool)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool}' not found")

    tool.workspace = workspace_dir
    tool.config = {}
    tool.telemetry = None

    try:
        result = tool.run(**req.args)
        return result
    except Exception as exc:
        logger.exception(f"Tool execution failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/browser")
async def browser_action(req: BrowserRequest):
    """
    Execute a Playwright browser action.
    Requires playwright + chromium installed in the sandbox image.
    """
    try:
        from sandbox.primitives.browser import run_browser_action  # type: ignore
    except ImportError:
        try:
            # Fallback: direct import when running inside container
            sys.path.insert(0, "/app")
            from sandbox.primitives.browser import run_browser_action  # type: ignore
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="Playwright not installed. Run: pip install playwright && playwright install chromium",
            )

    args = dict(req.args)
    args.setdefault("timeout", req.timeout)

    try:
        result = await run_browser_action(req.action, args)
        return result
    except Exception as exc:
        logger.exception(f"Browser action '{req.action}' failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/terminal")
def terminal_action(req: TerminalRequest):
    """Execute a shell command inside the sandbox container."""
    from sandbox.primitives.terminal import TerminalPrimitive  # type: ignore

    terminal = TerminalPrimitive()
    return terminal.run(command=req.command, timeout=req.timeout, cwd=req.cwd)


@app.post("/proxy")
def proxy_action(req: ProxyRequest):
    """Intercept / replay an HTTP request for manual exploit testing."""
    from sandbox.primitives.http_proxy import HttpProxyPrimitive  # type: ignore

    proxy = HttpProxyPrimitive(verify_ssl=False)
    return proxy.intercept(
        url=req.url,
        method=req.method,
        headers=req.headers or {},
        body=req.body,
        params=req.params,
        timeout=req.timeout,
        follow_redirects=req.follow_redirects,
    )


@app.post("/python")
def python_execute(req: PythonRequest):
    """
    Execute an arbitrary Python snippet in an isolated subprocess.
    stdout and stderr are captured and returned.
    """
    timeout = min(req.timeout, _MAX_TIMEOUT)
    logger.info(f"Executing Python snippet ({len(req.script)} chars, timeout={timeout}s)")
    try:
        result = subprocess.run(
            [sys.executable, "-c", req.script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success":   result.returncode == 0,
            "exit_code": result.returncode,
            "stdout":    result.stdout,
            "stderr":    result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "success":   False,
            "exit_code": -1,
            "stdout":    "",
            "stderr":    f"Script timed out after {timeout}s",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))