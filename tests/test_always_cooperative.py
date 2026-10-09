"""Behavioural checks for the ordinary-sharing control strategy."""
import pytest
import simulation as sim
from topology import build_edge_network, get_users, get_user_edge, get_cooperative_edges, add_to_cache


def setup_peer_case():
    network = build_edge_network(edges_per_region=3, users_per_region=3, cache_capacity=3, seed=42)
    user = get_users(network)[0]
    edge = get_user_edge(network, user)
    peers = get_cooperative_edges(network, edge)
    content = next(iter(sim.CONTENT))
    return network, user, edge, peers, content


def test_always_shares_even_when_game_rejects(monkeypatch):
    network, user, edge, peers, content = setup_peer_case()
    add_to_cache(network, peers[-1], content)
    monkeypatch.setattr(sim, 'should_cooperate', lambda *a, **k: False)
    game = sim.process_request(network.copy(), user, content, strategy='cooperative')
    assert game['result'] == 'origin_request'
    # NetworkX copies node attributes shallowly; rebuild to ensure fresh caches.
    network, user, edge, peers, content = setup_peer_case()
    add_to_cache(network, peers[-1], content)
    def forbidden(*args, **kwargs):
        raise AssertionError('Always-cooperative must not call the game or ML')
    monkeypatch.setattr(sim, 'should_cooperate', forbidden)
    monkeypatch.setattr(sim, 'generate_training_log', forbidden)
    result = sim.process_request(network, user, content, strategy='always_cooperative')
    assert result['result'] == 'cooperative_hit'
    assert result['source'] == peers[-1]
    assert result['bandwidth_used'] == 2 * sim.CONTENT[content]
    assert content in network.nodes[edge]['cache']
    assert sim.process_request(network, user, content, strategy='always_cooperative')['result'] == 'local_hit'
    sim.run_simulation(build_edge_network(), num_requests=5, strategy='always_cooperative')


def test_empty_peers_fall_back_to_origin():
    network, user, edge, peers, content = setup_peer_case()
    result = sim.process_request(network, user, content, strategy='always_cooperative')
    assert result['result'] == 'origin_request'
    assert content in network.nodes[edge]['cache']


def test_always_uses_same_requests_as_other_strategies():
    sequences = []
    for strategy in ['non_cooperative', 'always_cooperative', 'cooperative', 'ml_cooperative']:
        results = sim.run_simulation(build_edge_network(seed=42), num_requests=40, strategy=strategy, seed=42)
        sequences.append([(r['user'], r['content']) for r in results])
    assert all(sequence == sequences[0] for sequence in sequences)


def test_dashboard_graph_values_match_four_strategy_order():
    from app import prepare_graph_data
    keys = ['overall_hit_rate', 'average_latency', 'total_bandwidth_used', 'origin_requests', 'local_hits', 'cooperative_hits']
    summaries = [{key: i for key in keys} for i in range(4)]
    graphs = prepare_graph_data(*summaries)
    for graph in graphs.values():
        assert graph['labels'] == ['Non-Cooperative', 'Always-Cooperative', 'Game-Theoretic', 'ML Cooperative']
        for key, value in graph.items():
            if key != 'labels':
                assert value == [0, 1, 2, 3]
