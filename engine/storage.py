import os
import json
import tempfile
import logging
from pathlib import Path
from typing import Any, Dict, Optional

class AtomicFileStore:
    """
    Atomic file storage for BBH-AI data persistence.
    Ensures data integrity by writing to temp files and atomic moves.
    """
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.data_dir = self.workspace / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def save(self, key: str, data: Any) -> None:
        """Atomically save data to a file."""
        file_path = self.data_dir / f"{key}.json"
        temp_path = file_path.with_suffix('.tmp')
        
        try:
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            temp_path.replace(file_path)  # Atomic move
            self.logger.debug(f"Saved {key} to {file_path}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            self.logger.error(f"Failed to save {key}: {e}")
            raise

    def load(self, key: str) -> Optional[Any]:
        """Load data from file."""
        file_path = self.data_dir / f"{key}.json"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load {key}: {e}")
            return None

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return (self.data_dir / f"{key}.json").exists()