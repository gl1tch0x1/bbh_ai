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
    target_file = f"{tool_name}.py"
    module_path = None
    
    # Recursively search for the tool wrapper
    for root, dirs, files in os.walk(TOOLS_PATH):
        if target_file in files:
            module_path = os.path.join(root, target_file)
            break
            
    if not module_path or not os.path.exists(module_path):
        return None
        
    spec = importlib.util.spec_from_file_location(tool_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Handle cases like postleaks-ng -> PostleaksNgTool
    class_name = "".join(x.title() for x in tool_name.replace('-', '_').split('_')) + "Tool"
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