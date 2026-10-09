"""
Tests for demand_predictor.py.
"""

import pytest

from topology import build_edge_network, get_edge_servers
from simulation import CONTENT, CONTENT_POPULARITY_WEIGHTS
from demand_predictor import PopularityPredictor, generate_training_log


@pytest.fixture
def network():
    return build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )


@pytest.fixture
def trained_predictor(network):
    training_log = generate_training_log(
        network, CONTENT, CONTENT_POPULARITY_WEIGHTS,
        num_requests=100, seed=1
    )

    predictor = PopularityPredictor(CONTENT)
    predictor.fit(training_log)
    return predictor


def test_untrained_predictor_returns_zero_scores(network):
    predictor = PopularityPredictor(CONTENT)
    edge = get_edge_servers(network)[0]

    scores = predictor.predict_scores(edge, request_id=1)

    assert set(scores.keys()) == set(CONTENT.keys())
    assert all(score == 0.0 for score in scores.values())


def test_training_log_has_expected_length(network):
    log = generate_training_log(
        network, CONTENT, CONTENT_POPULARITY_WEIGHTS,
        num_requests=50, seed=1
    )

    assert len(log) == 50
    assert all(entry["content"] in CONTENT for entry in log)


def test_trained_predictor_scores_are_valid_probabilities(
    network, trained_predictor
):
    edge = get_edge_servers(network)[0]

    scores = trained_predictor.predict_scores(edge, request_id=101)

    assert set(scores.keys()) == set(CONTENT.keys())
    for score in scores.values():
        assert 0.0 <= score <= 1.0


def test_top_predictions_returns_known_content(network, trained_predictor):
    edge = get_edge_servers(network)[0]

    top = trained_predictor.top_predictions(edge, request_id=101, top_n=2)

    assert len(top) == 2
    assert all(item in CONTENT for item in top)
    assert len(set(top)) == 2  # no duplicates


def test_least_likely_returns_one_of_the_candidates(network, trained_predictor):
    edge = get_edge_servers(network)[0]
    candidates = list(CONTENT.keys())[:3]

    choice = trained_predictor.least_likely(
        edge, request_id=101, candidates=candidates
    )

    assert choice in candidates


def test_least_likely_returns_none_for_empty_candidates(
    network, trained_predictor
):
    edge = get_edge_servers(network)[0]

    assert trained_predictor.least_likely(
        edge, request_id=101, candidates=[]
    ) is None


def test_observe_updates_running_counters(network, trained_predictor):
    edge = get_edge_servers(network)[0]
    content = list(CONTENT.keys())[0]

    before = trained_predictor.frequency.get(edge, {}).get(content, 0)
    trained_predictor.observe(edge, content, request_id=101)
    after = trained_predictor.frequency.get(edge, {}).get(content, 0)

    assert after == before + 1
