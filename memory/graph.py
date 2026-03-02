class MemoryGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def add_node(self, node_id, data):
        self.nodes[node_id] = data

    def add_edge(self, from_node, to_node, relation):
        self.edges.append((from_node, to_node, relation))

    def query(self, **filters):
        results = []
        for node_id, data in self.nodes.items():
            if all(data.get(k) == v for k, v in filters.items()):
                results.append((node_id, data))
        return results