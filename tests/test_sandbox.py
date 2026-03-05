import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from sandbox import server


client = TestClient(server.app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_tools_listing():
    r = client.get("/tools")
    assert r.status_code == 200
    data = r.json()
    assert "tools" in data
    # tool list should be a list
    assert isinstance(data["tools"], list)


def test_execute_missing_tool(tmp_path, caplog):
    r = client.post("/execute", json={"tool": "nonexistent", "args": {}})
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]

# We can't execute a real tool without the binaries; simulate by creating a fake wrapper
@pytest.fixture(autouse=True)
def fake_tool(tmp_path, monkeypatch):
    # create temporary wrappers directory structure
    tools_dir = tmp_path / "wrappers"
    tools_dir.mkdir(parents=True, exist_ok=True)
    tool_file = tools_dir / "foobar.py"
    tool_file.write_text("""
class FoobarTool:
    def __init__(self, config, workspace, telemetry):
        self.workspace = workspace
    def run(self):
        return {"result": "ok", "workspace": self.workspace}
""")
    monkeypatch.setenv('TOOLS_PATH', str(tools_dir))
    # monkeypatch server.TOOLS_PATH
    server.TOOLS_PATH = str(tools_dir)
    yield


def test_execute_fake_tool(tmp_path):
    # This will use the fake tool above
    r = client.post("/execute", json={"tool": "foobar", "args": {}})
    assert r.status_code == 200
    resp = r.json()
    assert resp.get("result") == "ok"
    assert "/tmp" in resp.get("workspace", "")
