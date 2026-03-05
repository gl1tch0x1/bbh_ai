"""
sandbox/primitives/terminal.py — Shell Command Execution Primitive

Provides agents with a controlled terminal environment inside the sandbox
for command injection testing, OS command verification, and custom tool runs.
Strict timeout enforcement and no shell=True to prevent expansion attacks.
"""

import logging
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Hard upper-bound regardless of caller request
_MAX_TIMEOUT = 120


class TerminalPrimitive:
    """
    Wraps subprocess execution with strict security and resource controls.
    All commands run inside the sandbox container — never on the host.
    """

    def __init__(self, allowed_prefixes: Optional[List[str]] = None):
        """
        Args:
            allowed_prefixes: Optional whitelist of allowed command prefixes
                              (e.g. ['curl', 'nmap']). None = allow all inside sandbox.
        """
        self.allowed_prefixes = allowed_prefixes

    def run(
        self,
        command: Union[str, List[str]],
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a command and return structured output.

        Args:
            command: Shell command string or pre-split list of args.
            timeout: Execution timeout in seconds (max 120).
            cwd:     Working directory inside the container.
            env:     Additional environment variables to inject.

        Returns:
            {
                "success":   bool,
                "exit_code": int,
                "stdout":    str,
                "stderr":    str,
                "command":   str,
            }
        """
        timeout = min(int(timeout), _MAX_TIMEOUT)

        # Normalise to list — never use shell=True
        if isinstance(command, str):
            try:
                cmd_list = shlex.split(command)
            except ValueError as exc:
                return {"success": False, "error": f"Command parse error: {exc}"}
        else:
            cmd_list = list(command)

        if not cmd_list:
            return {"success": False, "error": "Empty command"}

        # Enforce whitelist if configured
        if self.allowed_prefixes:
            if cmd_list[0] not in self.allowed_prefixes:
                return {
                    "success": False,
                    "error": (
                        f"Command '{cmd_list[0]}' not in allowed list: "
                        f"{self.allowed_prefixes}"
                    ),
                }

        cmd_str = shlex.join(cmd_list)
        logger.info(f"[Terminal] Executing: {cmd_str!r} (timeout={timeout}s)")

        try:
            proc = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            return {
                "success":   proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout":    proc.stdout,
                "stderr":    proc.stderr,
                "command":   cmd_str,
            }
        except subprocess.TimeoutExpired:
            logger.warning(f"[Terminal] Command timed out after {timeout}s: {cmd_str!r}")
            return {
                "success":   False,
                "exit_code": -1,
                "stdout":    "",
                "stderr":    f"Command timed out after {timeout}s",
                "command":   cmd_str,
            }
        except FileNotFoundError:
            return {
                "success":   False,
                "exit_code": 127,
                "stdout":    "",
                "stderr":    f"Command not found: {cmd_list[0]!r}",
                "command":   cmd_str,
            }
        except Exception as exc:
            logger.error(f"[Terminal] Unexpected error: {exc}")
            return {
                "success":   False,
                "exit_code": -1,
                "stdout":    "",
                "stderr":    str(exc),
                "command":   cmd_str,
            }
