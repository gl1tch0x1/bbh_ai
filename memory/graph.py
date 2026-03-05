from typing import Any, Dict, List, Optional, Tuple, Union
import json
import logging
from pathlib import Path
from collections import defaultdict


class MemoryGraph:
    """
    Lightweight in-memory knowledge graph for tracking relationships between
    discovered assets, findings, and agents during a scan session.
    """

    def __init__(self, filepath: Optional[Path] = None) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}      # node_id → data dict
        self.edges: List[Tuple[str, str, str]] = []     # (from_id, to_id, relation)
        self._index: Dict[str, Any] = defaultdict(set)
        self.filepath = filepath
        self.logger = logging.getLogger(__name__)

        if self.filepath and self.filepath.exists():
            self.load()

    def add_node(self, node_id: str, data: Dict[str, Any]) -> None:
        """Add or update a node. Automatically indexes all key-value pairs."""
        self.nodes[node_id] = data
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)):
                self._index[f"{k}:{v}"].add(node_id)
        self.logger.debug(f"MemoryGraph: added node '{node_id}'")

    def add_edge(self, from_node: str, to_node: str, relation: str) -> None:
        """Add a directed edge between two nodes."""
        self.edges.append((from_node, to_node, relation))
        self.logger.debug(
            f"MemoryGraph: edge '{from_node}' -[{relation}]-> '{to_node}'"
        )

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a node data dictionary by ID."""
        return self.nodes.get(node_id)

    def query(self, **filters: Any) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Return list of (node_id, data) matching ALL filters.
        Uses the index for the first filter key to avoid full O(n) scan when possible.
        """
        if not filters:
            return list(self.nodes.items())

        # Use index for the first filter to narrow candidates
        items = list(filters.items())
        first_key, first_val = items[0]
        index_key = f"{first_key}:{first_val}"
        candidate_ids = self._index.get(index_key)

        if candidate_ids is None:
            return []

        results: List[Tuple[str, Dict[str, Any]]] = []
        for node_id in candidate_ids:
            data = self.nodes.get(node_id, {})
            if all(data.get(k) == v for k, v in filters.items()):
                results.append((node_id, data))
        return results

    def get_neighbors(self, node_id: str, relation: Optional[str] = None) -> List[str]:
        """Return neighbor node IDs connected from node_id (optionally filtered by relation)."""
        return [
            to for frm, to, rel in self.edges
            if frm == node_id and (relation is None or rel == relation)
        ]

    def summary(self) -> Dict[str, int]:
        """Return a statistical summary of the graph state."""
        return {"nodes": len(self.nodes), "edges": len(self.edges)}

    def save(self) -> None:
        """Persist the graph to the filesystem atomically."""
        if not self.filepath:
            return

        # Convert sets in _index to lists for JSON serialization
        index_serializable = {k: list(v) for k, v in self._index.items()}

        data = {
            "nodes": self.nodes,
            "edges": self.edges,
            "index": index_serializable,
        }

        # Atomic write: temp file then rename
        tmp_path = self.filepath.with_suffix('.tmp')
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            tmp_path.replace(self.filepath)
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink()
            self.logger.error(f"MemoryGraph save failed: {exc}")
            raise
        self.logger.debug(f"MemoryGraph saved to {self.filepath}")

    def load(self) -> None:
        """Load the graph from the filesystem."""
        if not self.filepath or not self.filepath.exists():
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.nodes = data.get("nodes", {})
            self.edges = [tuple(e) for e in data.get("edges", [])]

            # Rebuild index from lists to sets
            raw_index = data.get("index", {})
            self._index = defaultdict(set)
            for k, v in raw_index.items():
                self._index[k] = set(v)
            self.logger.debug(f"MemoryGraph loaded from {self.filepath}")
        except Exception as exc:
            self.logger.error(f"Failed to load MemoryGraph: {exc}")
