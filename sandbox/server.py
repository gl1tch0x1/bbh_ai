from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import logging
import os
import importlib.util
import sys

app = FastAPI()
logger = logging.getLogger("sandbox")
logging.basicConfig(level=logging.INFO)

TOOLS_PATH = "/app/tools/wrappers"
# default workspace inside container (persistent for life of container)
CONTAINER_WORKSPACE = "/tmp/bbh_workspace"

def load_tool(tool_name):
    target_file = f"{tool_name}.py"
    module_path = None
    
    # Recursively search for the tool wrapper
    for root, dirs, files in os.walk(TOOLS_PATH):
        if target_file in files:
            module_path = os.path.join(root, target_file)
            break
            
    if not module_path or not os.path.exists(module_path):
        return None
        
    try:
        spec = importlib.util.spec_from_file_location(tool_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error(f"Failed to import tool '{tool_name}' from {module_path}: {e}")
        return None
    
    # Handle cases like postleaks-ng -> PostleaksNgTool
    class_name = "".join(x.title() for x in tool_name.replace('-', '_').split('_')) + "Tool"
    tool_class = getattr(module, class_name, None)
    
    if tool_class:
        try:
            return tool_class(config={}, workspace=None, telemetry=None)
        except Exception as e:
            logger.error(f"Error instantiating tool '{tool_name}': {e}")
            return None
    return None

class ExecuteRequest(BaseModel):
    tool: str
    args: dict
    workspace: str | None = None  # host path mapped into container

@app.post("/execute")
def execute(req: ExecuteRequest):
    logger.info(f"Executing tool: {req.tool} with args {req.args} workspace={req.workspace}")

    # ensure workspace directory exists inside container
    # create a unique subdirectory per invocation to avoid race conditions
    import uuid, time
    base_dir = CONTAINER_WORKSPACE
    workspace_dir = os.path.join(base_dir, f"{req.tool}_{int(time.time())}_{uuid.uuid4().hex[:6]}")
    try:
        os.makedirs(workspace_dir, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create workspace dir {workspace_dir}: {e}")

    tool = load_tool(req.tool)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {req.tool} not found")

    # inject workspace path and basic config/telemetry placeholders
    # many wrappers expect `self.workspace` to be a Path-like
    tool.workspace = workspace_dir
    tool.config = {}  # no config available inside sandbox
    tool.telemetry = None

    try:
        result = tool.run(**req.args)
        return result
    except Exception as e:
        logger.exception(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tools")
def list_tools():
    tool_names = []
    for root, dirs, files in os.walk(TOOLS_PATH):
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                tool_names.append(os.path.splitext(f)[0])
    return {"tools": sorted(tool_names)}

@app.get("/health")
def health():
    return {"status": "ok"}