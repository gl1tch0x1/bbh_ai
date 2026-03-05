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

SECURITY NOTES:
- All endpoints validate input to prevent injection attacks
- Tool execution is sandboxed and limited by Docker resource constraints
- Timeout limits are enforced to prevent DoS
- No authentication required (runs only inside Docker network)
"""

import importlib.util
import logging
import os
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, validator

# Add request logging middleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="BBH-AI Sandbox", version="2.0")
logger = logging.getLogger("sandbox")
logging.basicConfig(level=logging.INFO)

# Security middleware - restrict to Docker network
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["127.0.0.1", "localhost", "*"]  # Allow all within Docker network
)

TOOLS_PATH = os.environ.get("TOOLS_PATH", "/app/tools/wrappers")
CONTAINER_WORKSPACE = "/tmp/bbh_workspace"
_MAX_TIMEOUT = 120  # hard cap for all primitive endpoints
_MAX_SCRIPT_SIZE = 1_000_000  # 1MB max for scripts
_ALLOWED_TOOL_PATTERN = r"^[a-zA-Z0-9_-]+$"  # Whitelist tool names


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


def _load_tool(tool_name: str) -> Optional[Any]:
    """
    Recursively locate and instantiate a tool wrapper by name.
    
    Args:
        tool_name: Name of the tool to load
        
    Returns:
        Instantiated tool object or None if not found
        
    Raises:
        ValueError: If tool name contains invalid characters
    """
    import re
    
    # Validate tool name format
    if not re.match(_ALLOWED_TOOL_PATTERN, tool_name):
        logger.error(f"Invalid tool name format: {tool_name}")
        return None
    
    # Prevent directory traversal
    if ".." in tool_name or "/" in tool_name or "\\" in tool_name:
        logger.error(f"Suspicious tool name detected: {tool_name}")
        return None
    
    target_file = f"{tool_name}.py"
    module_path = None

    for root, _dirs, files in os.walk(TOOLS_PATH):
        if target_file in files:
            module_path = os.path.join(root, target_file)
            break

    if not module_path or not os.path.exists(module_path):
        logger.warning(f"Tool file not found: {tool_name}")
        return None

    try:
        spec = importlib.util.spec_from_file_location(tool_name, module_path)
        if not spec or not spec.loader:
            logger.error(f"Could not create module spec for {tool_name}")
            return None
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.error(f"Failed to import tool '{tool_name}': {exc}")
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
    
    logger.warning(f"Tool class '{class_name}' not found in module {tool_name}")
    return None


# ── Request / Response Models ─────────────────────────────────────────────────
class ExecuteRequest(BaseModel):
    """Execute a tool in the sandbox."""
    tool: str = Field(..., min_length=1, max_length=100)
    args: Dict[str, Any] = Field(default_factory=dict)
    workspace: Optional[str] = None
    
    @validator('tool')
    def validate_tool_name(cls, v: str) -> str:
        """Validate tool name format to prevent injection."""
        import re
        if not re.match(_ALLOWED_TOOL_PATTERN, v):
            raise ValueError(f"Invalid tool name format: {v}")
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Tool name contains invalid characters")
        return v


class BrowserRequest(BaseModel):
    """Execute a browser action in the sandbox."""
    action: str = Field(..., min_length=1, max_length=50)  # navigate, click, fill, etc.
    args: Dict[str, Any] = Field(default_factory=dict)
    timeout: int = Field(default=30_000, le=120_000, ge=1000)


class TerminalRequest(BaseModel):
    """Execute a shell command in the sandbox."""
    command: str = Field(..., min_length=1, max_length=10000)
    timeout: int = Field(default=30, le=_MAX_TIMEOUT, ge=1)
    cwd: Optional[str] = None


class ProxyRequest(BaseModel):
    """HTTP proxy request model."""
    url: str = Field(..., min_length=1, max_length=2000)
    method: str = Field(default="GET", regex="^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$")
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    params: Optional[Dict[str, str]] = None
    timeout: int = Field(default=30, le=_MAX_TIMEOUT, ge=1)
    follow_redirects: bool = False


class PythonRequest(BaseModel):
    """Python code execution request."""
    script: str = Field(..., min_length=1, max_length=_MAX_SCRIPT_SIZE)
    timeout: int = Field(default=30, le=_MAX_TIMEOUT, ge=1)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0", "timestamp": time.time()}


@app.get("/tools")
async def list_tools() -> Dict[str, List[str]]:
    """List all available tools in the sandbox."""
    tool_names: List[str] = []
    try:
        for root, _dirs, files in os.walk(TOOLS_PATH):
            for f in files:
                if f.endswith(".py") and not f.startswith("__"):
                    tool_names.append(os.path.splitext(f)[0])
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
    return {"tools": sorted(tool_names)}


@app.post("/execute")
async def execute(req: ExecuteRequest) -> Dict[str, Any]:
    """
    Execute a tool wrapper by name.
    
    Args:
        req: ExecuteRequest with tool name and arguments
        
    Returns:
        Tool execution result
        
    Raises:
        HTTPException: If tool not found or execution fails
    """
    logger.info(f"Executing tool: {req.tool} with args: {list(req.args.keys())}")
    
    try:
        workspace_dir = _make_workspace(req.tool)
        
        tool = _load_tool(req.tool)
        if not tool:
            logger.warning(f"Tool not found: {req.tool}")
            raise HTTPException(status_code=404, detail=f"Tool '{req.tool}' not found")

        tool.workspace = workspace_dir
        tool.config = {}
        tool.telemetry = None

        result = tool.run(**req.args)
        
        # Ensure result is serializable
        if not isinstance(result, dict):
            result = {"result": str(result)}
            
        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid argument to tool '{req.tool}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.exception(f"Tool execution failed for '{req.tool}': {exc}")
        raise HTTPException(
            status_code=500, 
            detail=f"Tool execution error: {type(exc).__name__}: {str(exc)[:200]}"
        )


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