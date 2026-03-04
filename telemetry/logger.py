import json
import time
import threading
from pathlib import Path
from datetime import datetime
import gzip


class Telemetry:
    """
    Thread-safe telemetry collector that persists data to disk on save().
    Implements automatic file rotation to prevent unbounded growth.
    """

    def __init__(self, filepath, max_bytes: int = 10_485_760, backup_count: int = 5):
        """
        Initialize telemetry collector with rotation settings.
        
        Args:
            filepath: Path to telemetry.json file
            max_bytes: Maximum size before rotation (default 10MB)
            backup_count: Number of backup files to keep (default 5)
        """
        self.filepath = Path(filepath)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.Lock()
        self.data = {
            "start_time": time.time(),
            "start_time_iso": datetime.utcnow().isoformat() + "Z",
            "agent_logs": [],
            "tool_calls": [],
            "errors": [],
        }

    def log_agent_action(self, agent: str, action: str, details):
        """Log an agent action with thread safety."""
        entry = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.utcnow().isoformat() + "Z",
            "agent": str(agent),
            "action": str(action),
            "details": details,
        }
        with self._lock:
            self.data["agent_logs"].append(entry)

    def log_tool_call(self, tool: str, args: dict, result_summary):
        """Log a tool execution with thread safety."""
        entry = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.utcnow().isoformat() + "Z",
            "tool": str(tool),
            "args": args,
            "result_summary": result_summary,
        }
        with self._lock:
            self.data["tool_calls"].append(entry)

    def log_error(self, error):
        """Log an error with thread safety."""
        entry = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.utcnow().isoformat() + "Z",
            "error": str(error),
        }
        with self._lock:
            self.data["errors"].append(entry)

    def _rotate_files(self):
        """Rotate telemetry files when size limit is exceeded."""
        try:
            # Shift existing backup files and compress the current one
            for i in range(self.backup_count - 1, 0, -1):
                old_file = self.filepath.with_stem(f"{self.filepath.stem}.{i}")
                new_file = self.filepath.with_stem(f"{self.filepath.stem}.{i+1}")
                if old_file.exists():
                    old_file.rename(new_file)
            
            # Compress current file as .1
            if self.filepath.exists():
                backup_file = self.filepath.with_stem(f"{self.filepath.stem}.1")
                # Gzip compress the current telemetry for archival
                try:
                    with open(self.filepath, 'rb') as f_in:
                        with gzip.open(str(backup_file) + '.gz', 'wb') as f_out:
                            f_out.writelines(f_in)
                    self.filepath.unlink()  # Remove original after compression
                except Exception:
                    # If compression fails, just rename without compression
                    self.filepath.rename(backup_file)
        except Exception as e:
            print(f"[WARNING] Telemetry file rotation failed: {e}")

    def _should_rotate(self) -> bool:
        """Check if file rotation is needed."""
        if not self.filepath.exists():
            return False
        
        file_size = self.filepath.stat().st_size
        return file_size > self.max_bytes

    def save(self):
        """Persist telemetry data to disk. Called by Orchestrator in a finally block."""
        with self._lock:
            self.data["end_time"] = time.time()
            self.data["end_time_iso"] = datetime.utcnow().isoformat() + "Z"
            duration = self.data["end_time"] - self.data["start_time"]
            self.data["duration_seconds"] = round(duration, 2)
            payload = dict(self.data)

        try:
            # Ensure parent directory exists
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if rotation is needed before writing
            if self._should_rotate():
                self._rotate_files()
            
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, default=str)
        except Exception as e:
            # Don't raise, just log - telemetry failures shouldn't crash the app
            print(f"[WARNING] Failed to save telemetry to {self.filepath}: {e}")