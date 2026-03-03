import subprocess
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

class NmapTool:
    name = "nmap"
    categories = ["hosts", "discovery", "vuln"]
    
    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self.logger = logging.getLogger(__name__)
        self._timeout = (config or {}).get('scan', {}).get('timeout', 1200)

    def run(self, target: str, args: list = None) -> dict:
        self.logger.info(f"Running nmap on {target}...")
        output_file = self.workspace / f"nmap_{target}.xml"
        
        try:
            # Default args: -sV -T4 -oX
            cmd = ["nmap", "-sV", "-T4", "-oX", str(output_file), target]
            if args: cmd.extend(args)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            
            hosts = []
            if output_file.exists():
                hosts = self._parse_nmap_xml(output_file)
            
            output = {
                "tool": self.name,
                "inputs": {"target": target, "args": args},
                "outputs": {
                    "results": hosts,
                    "count": len(hosts)
                },
                "metadata": {"status": "success" if result.returncode == 0 else "warning"}
            }
            
            if self.telemetry:
                self.telemetry.log_tool_call(self.name, {"target": target}, output)
                
            return output

        except FileNotFoundError:
            return {"error": "nmap command not found. See https://nmap.org/"}
        except subprocess.TimeoutExpired:
            return {"error": "nmap command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_nmap_xml(self, xml_path: Path) -> list:
        """Parse nmap XML output into a structured list of hosts and ports."""
        hosts = []
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for host in root.findall('host'):
                addr = host.find('address').attrib.get('addr')
                status = host.find('status').attrib.get('state')
                
                ports = []
                for port in host.findall('.//port'):
                    port_id = port.attrib.get('portid')
                    state = port.find('state').attrib.get('state')
                    service = port.find('service')
                    service_name = service.attrib.get('name') if service is not None else "unknown"
                    
                    ports.append({
                        "port": port_id,
                        "state": state,
                        "service": service_name
                    })
                
                hosts.append({
                    "type": "host",
                    "value": addr,
                    "status": status,
                    "ports": ports
                })
        except Exception:
            pass
        return hosts
