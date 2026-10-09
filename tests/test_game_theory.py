"""
Tests for game_theory.py.

Includes a regression test for a real bug found during
development: under the original payoff constants, COOPERATE
strictly dominated DEFECT for every possible content size and
link quality, so the "game" never actually decided anything.
"""

import pytest

from topology import build_edge_network, get_edge_servers, get_cooperative_edges
from game_theory import (
    COOPERATE,
    DEFECT,
    calculate_cooperation_benefit,
    calculate_cooperation_cost,
    calculate_payoff,
    determine_strategies,
    should_cooperate,
    evaluate_network_cooperation
)


@pytest.fixture
def network():
    return build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )


def first_cooperative_pair(network):
    edge = get_edge_servers(network)[0]
    peer = get_cooperative_edges(network, edge)[0]
    return edge, peer


# ------------------------------------------------------------
# Basic sanity
# ------------------------------------------------------------

def test_strategies_are_always_valid_values(network):
    edge, peer = first_cooperative_pair(network)

    strategy_a, strategy_b = determine_strategies(
        network, edge, peer, content_size=100
    )

    assert strategy_a in (COOPERATE, DEFECT)
    assert strategy_b in (COOPERATE, DEFECT)


def test_mutual_defect_payoff_is_zero(network):
    edge, peer = first_cooperative_pair(network)

    payoff = calculate_payoff(
        network, edge, peer, content_size=100,
        strategy_a=DEFECT, strategy_b=DEFECT
    )

    assert payoff == 0.0


def test_should_cooperate_matches_determine_strategies(network):
    edge, peer = first_cooperative_pair(network)

    strategy_a, _ = determine_strategies(
        network, edge, peer, content_size=100
    )

    assert should_cooperate(
        network, edge, peer, content_size=100
    ) == (strategy_a == COOPERATE)


def test_benefit_and_cost_are_finite(network):
    edge, peer = first_cooperative_pair(network)

    benefit = calculate_cooperation_benefit(network, edge, peer, 100)
    cost = calculate_cooperation_cost(network, edge, peer, 100)

    assert benefit == benefit  # not NaN
    assert cost == cost
    assert cost != float("inf")


# ------------------------------------------------------------
# REGRESSION: cooperation must not be a foregone conclusion
# ------------------------------------------------------------

def test_cooperation_decision_is_not_always_the_same(network):
    """
    Guards against the original bug where COOPERATE won for
    every content size and every link quality. A real,
    working payoff model should produce different decisions
    for very different content sizes.
    """

    edge, peer = first_cooperative_pair(network)

    decisions = set()

    for size in [0.01, 0.1, 1, 10, 100, 1000]:
        strategy_a, _ = determine_strategies(
            network, edge, peer, content_size=size
        )
        decisions.add(strategy_a)

    assert len(decisions) == 2, (
        "Expected both COOPERATE and DEFECT to occur across a "
        "wide range of content sizes - if this fails, check "
        "whether the payoff model has collapsed to always "
        "picking one strategy regardless of input."
    )


def test_larger_content_is_at_least_as_likely_to_cooperate(network):
    """
    Benefit scales with content size (more data = more time
    saved by avoiding the origin), while cost does not. So
    bigger content should never make cooperation LESS likely
    for the same pair.
    """

    edge, peer = first_cooperative_pair(network)

    small_benefit = calculate_cooperation_benefit(network, edge, peer, 1)
    large_benefit = calculate_cooperation_benefit(network, edge, peer, 1000)

    assert large_benefit > small_benefit


def test_evaluate_network_cooperation_covers_all_pairs(network):
    decisions = evaluate_network_cooperation(network, content_size=100)

    # 4 regions x 1 cooperative pair each (2 edges/region)
    assert len(decisions) == 4

    for decision in decisions.values():
        assert decision["strategy_a"] in (COOPERATE, DEFECT)
        assert decision["strategy_b"] in (COOPERATE, DEFECT)
