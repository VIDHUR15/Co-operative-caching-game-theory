"""
Tests for simulation.py.
"""

import pytest

from topology import build_edge_network
from simulation import (
    CONTENT,
    CONTENT_POPULARITY_WEIGHTS,
    generate_request,
    get_users,
    process_request,
    run_simulation,
    get_simulation_summary
)


@pytest.fixture
def network():
    return build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )


# ------------------------------------------------------------
# Content catalog
# ------------------------------------------------------------

def test_content_and_weights_same_length():
    assert len(CONTENT) == len(CONTENT_POPULARITY_WEIGHTS)


def test_all_content_sizes_positive():
    assert all(size > 0 for size in CONTENT.values())


def test_all_popularity_weights_positive():
    assert all(w > 0 for w in CONTENT_POPULARITY_WEIGHTS)


# ------------------------------------------------------------
# Request generation
# ------------------------------------------------------------

def test_generate_request_returns_valid_user_and_content(network):
    users = get_users(network)

    user, content = generate_request(users, CONTENT)

    assert user in users
    assert content in CONTENT


# ------------------------------------------------------------
# process_request
# ------------------------------------------------------------

def test_process_request_returns_a_known_outcome(network):
    users = get_users(network)
    user, content = generate_request(users, CONTENT)

    result = process_request(network, user, content, strategy="cooperative")

    assert result["result"] in (
        "local_hit", "cooperative_hit", "origin_request"
    )
    assert result["latency"] >= 0
    assert result["bandwidth_used"] > 0


def test_repeated_request_for_same_content_becomes_local_hit(network):
    users = get_users(network)
    user = users[0]
    content = list(CONTENT.keys())[0]

    first = process_request(network, user, content, strategy="non_cooperative")
    second = process_request(network, user, content, strategy="non_cooperative")

    # First touch caches it (unless it was already a hit);
    # second touch must be a local hit either way.
    assert second["result"] == "local_hit"


# ------------------------------------------------------------
# run_simulation / get_simulation_summary, all 3 strategies
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "strategy",
    ["non_cooperative", "always_cooperative", "cooperative", "ml_cooperative"]
)
def test_run_simulation_produces_one_result_per_request(strategy):
    network = build_edge_network(
        edges_per_region=2, users_per_region=2,
        cache_capacity=3, seed=42
    )

    results = run_simulation(
        network, num_requests=50, strategy=strategy, seed=42
    )

    assert len(results) == 50


@pytest.mark.parametrize(
    "strategy",
    ["non_cooperative", "always_cooperative", "cooperative", "ml_cooperative"]
)
def test_summary_counts_add_up_to_total(strategy):
    network = build_edge_network(
        edges_per_region=2, users_per_region=2,
        cache_capacity=3, seed=42
    )

    results = run_simulation(
        network, num_requests=200, strategy=strategy, seed=42
    )
    summary = get_simulation_summary(results)

    assert (
        summary["local_hits"]
        + summary["cooperative_hits"]
        + summary["demand_origin_requests"]
        == summary["total_requests"]
    )
    assert summary["total_requests"] == 200


def test_non_cooperative_strategy_never_has_cooperative_hits():
    network = build_edge_network(
        edges_per_region=2, users_per_region=2,
        cache_capacity=3, seed=42
    )

    results = run_simulation(
        network, num_requests=200, strategy="non_cooperative", seed=42
    )
    summary = get_simulation_summary(results)

    assert summary["cooperative_hits"] == 0


def test_same_seed_gives_reproducible_results():
    def run():
        network = build_edge_network(
            edges_per_region=2, users_per_region=2,
            cache_capacity=3, seed=42
        )
        results = run_simulation(
            network, num_requests=100, strategy="cooperative", seed=42
        )
        return get_simulation_summary(results)

    summary_a = run()
    summary_b = run()

    assert summary_a == summary_b


def test_smaller_cache_capacity_does_not_increase_hit_rate():
    """
    A smaller cache can never do strictly better than a
    larger one under the same policy - if this fails, cache
    capacity or eviction is behaving backwards.
    """

    def hit_rate(capacity):
        network = build_edge_network(
            edges_per_region=2, users_per_region=2,
            cache_capacity=capacity, seed=42
        )
        results = run_simulation(
            network, num_requests=300, strategy="cooperative", seed=42
        )
        return get_simulation_summary(results)["overall_hit_rate"]

    assert hit_rate(capacity=1) <= hit_rate(capacity=5)
