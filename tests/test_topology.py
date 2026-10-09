"""
Tests for topology.py.

Includes regression tests for two real bugs found during
development:
  - add_to_cache() used to evict an arbitrary item (set.pop())
    instead of the least-recently-used one.
  - edge servers beyond users_per_region were silently left
    with no users and could never affect results.
"""

import warnings

import pytest

from topology import (
    build_edge_network,
    get_edge_servers,
    get_users,
    get_user_edge,
    get_cooperative_edges,
    get_link_info,
    add_to_cache,
    touch_cache,
    calculate_transfer_time,
    haversine_distance,
    REGION_COORDINATES,
    ORIGIN_COORDINATE
)


def build_test_network(**overrides):
    params = dict(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )
    params.update(overrides)
    return build_edge_network(**params)


# ------------------------------------------------------------
# Basic topology shape
# ------------------------------------------------------------

def test_network_has_expected_node_counts():
    network = build_test_network()

    edges = get_edge_servers(network)
    users = get_users(network)

    # 4 default regions x 2 edges/region, x 2 users/region
    assert len(edges) == 8
    assert len(users) == 8


def test_every_user_is_connected_to_an_edge():
    network = build_test_network()

    for user in get_users(network):
        edge = get_user_edge(network, user)
        assert edge is not None
        assert edge in get_edge_servers(network)


def test_cooperative_edges_are_same_region_only():
    network = build_test_network()

    for edge in get_edge_servers(network):
        region = network.nodes[edge]["region"]

        for peer in get_cooperative_edges(network, edge):
            assert network.nodes[peer]["region"] == region


def test_build_is_reproducible_with_same_seed():
    network_a = build_test_network(seed=7)
    network_b = build_test_network(seed=7)

    edge = get_edge_servers(network_a)[0]
    peer = get_cooperative_edges(network_a, edge)[0]

    link_a = get_link_info(network_a, edge, peer)
    link_b = get_link_info(network_b, edge, peer)

    assert link_a == link_b


# ------------------------------------------------------------
# REGRESSION: real LRU eviction (was arbitrary set.pop())
# ------------------------------------------------------------

def test_cache_never_exceeds_capacity():
    network = build_test_network(cache_capacity=2)
    edge = get_edge_servers(network)[0]

    for content in ["A", "B", "C", "D", "E"]:
        add_to_cache(network, edge, content)
        assert len(network.nodes[edge]["cache"]) <= 2


def test_eviction_removes_least_recently_used_item():
    network = build_test_network(cache_capacity=2)
    edge = get_edge_servers(network)[0]

    add_to_cache(network, edge, "A")
    add_to_cache(network, edge, "B")

    # Touching A makes B the least-recently-used item.
    touch_cache(network, edge, "A")

    add_to_cache(network, edge, "C")

    cache = network.nodes[edge]["cache"]
    assert "A" in cache
    assert "C" in cache
    assert "B" not in cache


def test_readding_cached_item_does_not_evict_anything():
    network = build_test_network(cache_capacity=2)
    edge = get_edge_servers(network)[0]

    add_to_cache(network, edge, "A")
    add_to_cache(network, edge, "B")
    add_to_cache(network, edge, "A")  # already cached

    cache = network.nodes[edge]["cache"]
    assert len(cache) == 2
    assert "A" in cache and "B" in cache


# ------------------------------------------------------------
# REGRESSION: idle edge servers when users < edges per region
# ------------------------------------------------------------

def test_warns_when_users_fewer_than_edges_per_region():
    with pytest.warns(UserWarning):
        build_test_network(edges_per_region=4, users_per_region=2)


def test_no_warning_when_users_at_least_edges_per_region():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        # Should NOT raise
        build_test_network(edges_per_region=2, users_per_region=2)


def test_every_edge_has_at_least_one_user_when_matched():
    network = build_test_network(edges_per_region=3, users_per_region=3)

    served = {
        get_user_edge(network, user)
        for user in get_users(network)
    }

    assert served == set(get_edge_servers(network))


# ------------------------------------------------------------
# Transfer time / distance math
# ------------------------------------------------------------

def test_transfer_time_increases_with_content_size():
    small = calculate_transfer_time(10, bandwidth=100, latency=5)
    large = calculate_transfer_time(1000, bandwidth=100, latency=5)
    assert large > small


def test_transfer_time_decreases_with_bandwidth():
    slow = calculate_transfer_time(100, bandwidth=10, latency=5)
    fast = calculate_transfer_time(100, bandwidth=1000, latency=5)
    assert fast < slow


def test_haversine_distance_zero_for_same_point():
    assert haversine_distance(
        REGION_COORDINATES["US-East"],
        REGION_COORDINATES["US-East"]
    ) == pytest.approx(0.0, abs=1e-6)


def test_haversine_distance_is_symmetric():
    a = REGION_COORDINATES["US-East"]
    b = REGION_COORDINATES["Asia"]

    assert haversine_distance(a, b) == pytest.approx(
        haversine_distance(b, a)
    )


def test_asia_is_farther_from_origin_than_us_east():
    d_us_east = haversine_distance(
        ORIGIN_COORDINATE, REGION_COORDINATES["US-East"]
    )
    d_asia = haversine_distance(
        ORIGIN_COORDINATE, REGION_COORDINATES["Asia"]
    )

    assert d_asia > d_us_east
