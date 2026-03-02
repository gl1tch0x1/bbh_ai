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

def load_tool(tool_name):
    module_path = os.path.join(TOOLS_PATH, f"{tool_name}.py")
    if not os.path.exists(module_path):
        return None
    spec = importlib.util.spec_from_file_location(tool_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class_name = f"{tool_name.title().replace('_', '')}Tool"
    tool_class = getattr(module, class_name, None)
    if tool_class:
        return tool_class(config={}, workspace=None, telemetry=None)
    return None

class ExecuteRequest(BaseModel):
    tool: str
    args: dict

@app.post("/execute")
def execute(req: ExecuteRequest):
    logger.info(f"Executing tool: {req.tool} with args {req.args}")
    tool = load_tool(req.tool)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {req.tool} not found")
    try:
        result = tool.run(**req.args)
        return result
    except Exception as e:
        logger.exception(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}