import os
import tempfile

from main import expand_env_vars
from memory.graph import MemoryGraph


def test_expand_env_vars_simple(tmp_path, monkeypatch):
    monkeypatch.setenv('FOO', 'bar')
    cfg = {'a': '$FOO', 'b': ['${FOO}', 'baz'], 'c': {'nested': '$FOO$FOO'}}
    out = expand_env_vars(cfg)
    assert out['a'] == 'bar'
    assert out['b'][0] == 'bar'
    assert out['c']['nested'] == 'barbar'


def test_memory_graph_add_query(tmp_path):
    path = tmp_path / "graph.json"
    mg = MemoryGraph(path)
    mg.add_node('n1', {'type': 'subdomain', 'value': 'example.com'})
    mg.add_node('n2', {'type': 'subdomain', 'value': 'example.org'})
    mg.add_edge('n1', 'n2', 'related')

    assert mg.get_node('n1')['value'] == 'example.com'
    results = mg.query(type='subdomain')
    assert len(results) == 2
    neighbors = mg.get_neighbors('n1')
    assert 'n2' in neighbors
    mg.save()
    assert path.exists()
    mg2 = MemoryGraph(path)
    assert mg2.get_node('n2')['value'] == 'example.org'
