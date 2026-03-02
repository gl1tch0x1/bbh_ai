import logging
from collections import defaultdict


class MemoryGraph:
    """
    Lightweight in-memory knowledge graph for tracking relationships between
    discovered assets, findings, and agents during a scan session.
    """

    def __init__(self):
        self.nodes: dict = {}                          # node_id → data dict
        self.edges: list = []                          # (from_id, to_id, relation)
        self._index: dict = defaultdict(set)           # key:value → set of node_ids
        self.logger = logging.getLogger(__name__)

    def add_node(self, node_id: str, data: dict) -> None:
        """Add or update a node. Automatically indexes all key-value pairs."""
        self.nodes[node_id] = data
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)):
                self._index[f"{k}:{v}"].add(node_id)
        self.logger.debug(f"MemoryGraph: added node '{node_id}'")

    def add_edge(self, from_node: str, to_node: str, relation: str) -> None:
        """Add a directed edge between two nodes."""
        self.edges.append((from_node, to_node, relation))
        self.logger.debug(f"MemoryGraph: edge '{from_node}' -[{relation}]-> '{to_node}'")

    def get_node(self, node_id: str) -> dict | None:
        """Retrieve a node by ID."""
        return self.nodes.get(node_id)

    def query(self, **filters) -> list[tuple]:
        """
        Return list of (node_id, data) matching ALL filters.
        Uses the index for the first filter key to avoid full O(n) scan when possible.
        """
        if not filters:
            return list(self.nodes.items())

        # Use index for the first filter to narrow candidates
        items = filters.items()
        first_key, first_val = next(iter(items))
        index_key = f"{first_key}:{first_val}"
        candidate_ids = self._index.get(index_key, set(self.nodes.keys()))

        results = []
        for node_id in candidate_ids:
            data = self.nodes.get(node_id, {})
            if all(data.get(k) == v for k, v in filters.items()):
                results.append((node_id, data))
        return results

    def get_neighbors(self, node_id: str, relation: str = None) -> list[str]:
        """Return neighbor node IDs connected from node_id (optionally filtered by relation)."""
        return [
            to for frm, to, rel in self.edges
            if frm == node_id and (relation is None or rel == relation)
        ]

    def summary(self) -> dict:
        return {"nodes": len(self.nodes), "edges": len(self.edges)}