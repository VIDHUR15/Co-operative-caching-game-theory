import pytest
import simulation as sim
from topology import build_edge_network, get_users, get_user_edge, get_link_info, calculate_transfer_time, add_to_cache
from demand_predictor import PopularityPredictor


class FixedPrediction:
    def __init__(self, item): self.item = item
    def top_predictions(self, *args, **kwargs): return [self.item]


def setup():
    g = build_edge_network(cache_capacity=3)
    user = get_users(g)[0]
    edge = get_user_edge(g, user)
    items = list(sim.CONTENT)
    return g, user, edge, items


def test_prefetch_current_item_is_charged_once_and_is_not_a_hit():
    g, user, edge, items = setup()
    item = items[0]
    r = sim.process_request(g, user, item, 'ml_cooperative', FixedPrediction(item), 201)
    region = g.nodes[edge]['region']
    links = [get_link_info(g, 'Origin', region), get_link_info(g, region, edge), get_link_info(g, edge, user)]
    expected = sum(calculate_transfer_time(sim.CONTENT[item], l['bandwidth'], l['latency']) for l in links)
    assert r['latency'] == pytest.approx(expected)
    assert r['bandwidth_used'] == sim.CONTENT[item] * 3
    assert r['result'] == 'origin_request'
    summary = sim.get_simulation_summary([r])
    assert summary['overall_hit_rate'] == 0
    assert summary['origin_requests'] == 1
    assert summary['prefetch_origin_requests'] == 1
    assert summary['demand_fetch_origin_requests'] == 0
    later = sim.process_request(g, user, item, 'ml_cooperative', FixedPrediction(item), 202)
    assert later['result'] == 'local_hit'
    assert later['prefetch_origin_requests'] == 0


def test_unused_prefetch_and_demand_fetch_are_both_counted():
    g, user, edge, items = setup()
    r = sim.process_request(g, user, items[1], 'ml_cooperative', FixedPrediction(items[0]), 201)
    summary = sim.get_simulation_summary([r])
    assert summary['origin_requests'] == 2
    assert summary['demand_origin_requests'] == 1
    assert summary['total_bandwidth_used'] == 2*sim.CONTENT[items[0]] + 3*sim.CONTENT[items[1]]
    assert r['latency'] == pytest.approx(r['payload_latency_ms'] + r['coordination_latency_ms'] + r['prefetch_latency_ms'])


def test_full_cache_does_not_prefetch():
    g, user, edge, items = setup()
    for item in items[:3]: add_to_cache(g, edge, item)
    r = sim.process_request(g, user, items[0], 'ml_cooperative', FixedPrediction(items[3]), 201)
    assert r['prefetch_origin_requests'] == 0
    assert r['prefetch_latency_ms'] == 0


def test_prediction_and_observation_timeline_continues_after_training(monkeypatch):
    old_predict = PopularityPredictor.predict_scores
    observed_times = []
    old_observe = PopularityPredictor.observe
    def checked_predict(self, edge, request_id):
        assert request_id > 200
        assert all(row['recency_gap'] >= 0 for row in self._rows_for_edge(edge, request_id))
        return old_predict(self, edge, request_id)
    def checked_observe(self, edge, content, request_id):
        observed_times.append(request_id)
        return old_observe(self, edge, content, request_id)
    monkeypatch.setattr(PopularityPredictor, 'predict_scores', checked_predict)
    monkeypatch.setattr(PopularityPredictor, 'observe', checked_observe)
    r = sim.run_simulation(build_edge_network(), num_requests=30, strategy='ml_cooperative')
    assert observed_times == list(range(201, 231))
    assert [x['request_id'] for x in r] == list(range(1,31))
    assert [x['model_request_id'] for x in r] == observed_times
