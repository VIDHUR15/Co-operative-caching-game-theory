import pytest
import simulation as sim
from topology import build_edge_network, get_users, get_user_edge, get_cooperative_edges, add_to_cache
from game_theory import calculate_cooperation_cost


def case():
    g = build_edge_network(edges_per_region=3, users_per_region=3, cache_capacity=3, seed=42)
    user = get_users(g)[0]
    edge = get_user_edge(g, user)
    peers = get_cooperative_edges(g, edge)
    return g, user, edge, peers, next(iter(sim.CONTENT))


def test_rejected_cached_peer_cannot_serve(monkeypatch):
    g, user, edge, peers, item = case()
    add_to_cache(g, peers[0], item)
    monkeypatch.setattr(sim, 'should_cooperate', lambda network, a, b, size: b == peers[1])
    r = sim.process_request(g, user, item, 'cooperative')
    assert r['source'] == 'Origin'
    assert [a['peer'] for a in r['peer_attempts']] == [peers[1]]
    assert r['coordination_latency_ms'] == pytest.approx(calculate_cooperation_cost(g, edge, peers[1], sim.CONTENT[item]))


def test_fastest_approved_peer_is_selected_and_cost_counted_once(monkeypatch):
    g, user, edge, peers, item = case()
    for peer in peers:
        add_to_cache(g, peer, item)
    g.edges[edge, peers[0]].update(latency=100, bandwidth=10)
    g.edges[edge, peers[1]].update(latency=1, bandwidth=1000)
    monkeypatch.setattr(sim, 'should_cooperate', lambda *args: True)
    r = sim.process_request(g, user, item, 'cooperative')
    assert r['source'] == peers[1]
    assert r['peer_checks'] == 1
    assert r['coordination_latency_ms'] == 12
    assert r['latency'] == pytest.approx(r['payload_latency_ms'] + 12)


def test_always_baseline_pays_for_misses_and_success():
    g, user, edge, peers, item = case()
    add_to_cache(g, peers[1], item)
    r = sim.process_request(g, user, item, 'always_cooperative')
    expected = sum(calculate_cooperation_cost(g, edge, peer, sim.CONTENT[item]) for peer in peers)
    assert r['peer_checks'] == 2
    assert [a['hit'] for a in r['peer_attempts']] == [False, True]
    assert r['coordination_latency_ms'] == pytest.approx(expected)
    assert r['latency'] == pytest.approx(r['payload_latency_ms'] + expected)
    local = sim.process_request(g, user, item, 'always_cooperative')
    assert local['coordination_latency_ms'] == 0
    assert local['peer_checks'] == 0


def test_failed_queries_are_charged_on_origin_fallback():
    g, user, edge, peers, item = case()
    r = sim.process_request(g, user, item, 'always_cooperative')
    assert r['result'] == 'origin_request'
    assert r['peer_checks'] == 2
    assert r['coordination_latency_ms'] > 0
    summary = sim.get_simulation_summary([r])
    assert summary['total_peer_checks'] == 2
    assert summary['average_coordination_latency_ms'] == r['coordination_latency_ms']
    assert summary['average_latency'] == r['payload_latency_ms'] + r['coordination_latency_ms']


def test_rejected_links_do_not_incur_query_cost(monkeypatch):
    g, user, edge, peers, item = case()
    monkeypatch.setattr(sim, 'should_cooperate', lambda *args: False)
    r = sim.process_request(g, user, item, 'cooperative')
    assert r['peer_checks'] == 0
    assert r['coordination_latency_ms'] == 0
    assert len(r['peer_decisions']) == 2


def test_real_game_rejects_slow_peer_while_always_pays_for_it():
    results = {}
    for strategy in ['cooperative', 'always_cooperative']:
        g, user, edge, peers, item = case()
        for peer in peers:
            g.edges[edge, peer].update(latency=1000, bandwidth=0.1)
            add_to_cache(g, peer, item)
        results[strategy] = sim.process_request(g, user, item, strategy)
    assert results['cooperative']['result'] == 'origin_request'
    assert results['always_cooperative']['result'] == 'cooperative_hit'
    assert results['cooperative']['latency'] < results['always_cooperative']['latency']
