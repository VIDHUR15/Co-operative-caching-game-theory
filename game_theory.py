"""
Simplified game-inspired payoff policy for peer retrieval.

Actions refer to the requesting edge's route choice:
COOPERATE -> try retrieving from a peer; DEFECT -> use the origin.
They do NOT represent permission to serve content. Connected peers remain
willing to serve cached items regardless of their own retrieval preference.
Hence A may benefit from B while B chooses origin for its own requests.
The pairwise best-response calculation adds a small modeled utility bonus
when both prefer peer retrieval. This is not a bilateral sharing agreement,
a fairness model, or proof of global optimality. The bonus is not a physical
latency saving. should_cooperate returns only the requester's route choice.
"""

from topology import (
    build_edge_network,
    get_edge_servers,
    get_cooperative_edges,
    get_link_info,
    calculate_transfer_time
)


# ============================================================
# STRATEGIES
# ============================================================

COOPERATE = "cooperate"
DEFECT = "defect"


# ============================================================
# GAME PARAMETERS
# ============================================================

DEFAULT_PARAMETERS = {
    # Extra fixed overhead of a cooperative request beyond the
    # round-trip already counted in calculate_cooperation_cost
    # (connection setup, cache lookup bookkeeping on the
    # serving edge). A small, citable number, not a free knob
    # picked to produce a nice-looking split.
    "coordination_overhead_ms": 10.0,

    # Small tiebreaker for genuine near-ties, representing the
    # intangible value of an established cooperative
    # relationship (a "warmer" cache, less renegotiation next
    # time). Kept deliberately small - a few ms - so it only
    # swings decisions that are already close, rather than
    # overriding the real time savings computed below.
    "mutual_cooperation_bonus_ms": 2.0
}


# ============================================================
# CALCULATE COOPERATION BENEFIT
# ============================================================

def calculate_cooperation_benefit(
    network,
    edge_a,
    edge_b,
    content_size,
    parameters=None
):
    """
    Calculates the benefit of edge_a cooperating with edge_b,
    in real milliseconds: how much faster it is to fetch
    content_size from edge_b than to go all the way to the
    origin server.

    This is computed with calculate_transfer_time() - the
    exact same function simulation.py uses to produce its
    actual latency results - so benefit is always in the
    same real units as the rest of the project, and scales
    correctly on its own whether content_size is a 1000MB
    video or a 50KB Wikipedia article. No re-tuning needed
    when the dataset changes scale.

    Can be negative: if the cooperative link is actually
    slower than the origin backbone, cooperating is
    genuinely not worth it, and this reflects that honestly
    instead of assuming cooperation always helps.
    """

    if parameters is None:
        parameters = DEFAULT_PARAMETERS

    cooperative_link = get_link_info(
        network,
        edge_a,
        edge_b
    )

    if cooperative_link is None:
        return 0.0

    cooperative_time = calculate_transfer_time(
        content_size,
        cooperative_link["bandwidth"],
        cooperative_link["latency"]
    )

    # Real origin path: edge -> region -> Origin
    region = network.nodes[edge_a]["region"]

    edge_region_link = get_link_info(
        network,
        edge_a,
        region
    )

    region_origin_link = get_link_info(
        network,
        region,
        "Origin"
    )

    if edge_region_link is None or region_origin_link is None:
        return 0.0

    origin_time = (
        calculate_transfer_time(
            content_size,
            edge_region_link["bandwidth"],
            edge_region_link["latency"]
        )
        + calculate_transfer_time(
            content_size,
            region_origin_link["bandwidth"],
            region_origin_link["latency"]
        )
    )

    return origin_time - cooperative_time


# ============================================================
# CALCULATE COOPERATION COST
# ============================================================

def calculate_cooperation_cost(
    network,
    edge_a,
    edge_b,
    content_size,
    parameters=None
):
    """
    Calculates the cost incurred when edge_a asks edge_b to
    cooperate, in real milliseconds.

    Cost = one extra round-trip over the real cooperative
    link (to check/request the content from the peer, on top
    of the transfer already counted in the benefit) + a small
    fixed coordination overhead (connection setup, cache
    lookup bookkeeping).

    Unlike the previous unitless cost formula, this doesn't
    need re-tuning when content_size changes scale - it's
    tied to the link's own real latency, and content_size
    doesn't otherwise appear here (asking whether content
    exists on a peer costs the same regardless of how big
    that content turns out to be).
    """

    if parameters is None:
        parameters = DEFAULT_PARAMETERS

    link = get_link_info(
        network,
        edge_a,
        edge_b
    )

    if link is None:
        return float("inf")

    # Round-trip (there and back) to check/request content
    # from the peer, over the real measured link latency.
    round_trip_cost = 2 * link["latency"]

    return (
        round_trip_cost
        + parameters["coordination_overhead_ms"]
    )


# ============================================================
# CALCULATE PAYOFF
# ============================================================

def calculate_payoff(
    network,
    edge_a,
    edge_b,
    content_size,
    strategy_a,
    strategy_b,
    parameters=None
):
    """
    Calculates the payoff for edge_a.

    Parameters
    ----------
    edge_a : str
        First edge server.

    edge_b : str
        Second edge server.

    content_size : float
        Content size in MB.

    strategy_a : str
        Strategy selected by edge_a.

    strategy_b : str
        Strategy selected by edge_b.

    Returns
    -------
    float
        Payoff for edge_a.
    """

    if parameters is None:
        parameters = DEFAULT_PARAMETERS

    benefit = calculate_cooperation_benefit(
        network,
        edge_a,
        edge_b,
        content_size,
        parameters
    )

    cost = calculate_cooperation_cost(
        network,
        edge_a,
        edge_b,
        content_size,
        parameters
    )

    # --------------------------------------------------------
    # Both cooperate
    # --------------------------------------------------------

    if (
        strategy_a == COOPERATE
        and strategy_b == COOPERATE
    ):

        return (
            parameters["mutual_cooperation_bonus_ms"]
            + benefit
            - cost
        )

    # --------------------------------------------------------
    # A chooses peer retrieval, B prefers origin for its own retrieval
    # --------------------------------------------------------

    elif (
        strategy_a == COOPERATE
        and strategy_b == DEFECT
    ):

        return (
            benefit
            - cost
        )

    # --------------------------------------------------------
    # A defects, B cooperates
    # --------------------------------------------------------

    elif (
        strategy_a == DEFECT
        and strategy_b == COOPERATE
    ):

        return 0.0

    # --------------------------------------------------------
    # Both defect
    # --------------------------------------------------------

    else:

        return 0.0


# ============================================================
# CREATE PAYOFF MATRIX
# ============================================================

def create_payoff_matrix(
    network,
    edge_a,
    edge_b,
    content_size,
    parameters=None
):
    """
    Creates the payoff matrix for two edge servers.

    Returns a dictionary containing the payoff of each
    player for every strategy combination.
    """

    matrix = {}

    strategies = [
        COOPERATE,
        DEFECT
    ]

    for strategy_a in strategies:

        for strategy_b in strategies:

            payoff_a = calculate_payoff(
                network,
                edge_a,
                edge_b,
                content_size,
                strategy_a,
                strategy_b,
                parameters
            )

            payoff_b = calculate_payoff(
                network,
                edge_b,
                edge_a,
                content_size,
                strategy_b,
                strategy_a,
                parameters
            )

            matrix[
                (strategy_a, strategy_b)
            ] = (
                payoff_a,
                payoff_b
            )

    return matrix


# ============================================================
# FIND BEST STRATEGY
# ============================================================

def find_best_strategy(
    network,
    edge_a,
    edge_b,
    content_size,
    opponent_strategy,
    parameters=None
):
    """
    Determines the best strategy for edge_a given the
    strategy chosen by edge_b.

    Returns:
        COOPERATE or DEFECT
    """

    cooperate_payoff = calculate_payoff(
        network,
        edge_a,
        edge_b,
        content_size,
        COOPERATE,
        opponent_strategy,
        parameters
    )

    defect_payoff = calculate_payoff(
        network,
        edge_a,
        edge_b,
        content_size,
        DEFECT,
        opponent_strategy,
        parameters
    )

    if cooperate_payoff >= defect_payoff:
        return COOPERATE

    return DEFECT


# ============================================================
# DETERMINE MUTUAL STRATEGIES
# ============================================================

def determine_strategies(
    network,
    edge_a,
    edge_b,
    content_size,
    parameters=None
):
    """
    Determines the strategies selected by both edge servers.

    The decision is based on the calculated payoffs.
    """

    # Initially assume both cooperate
    strategy_a = COOPERATE
    strategy_b = COOPERATE

    # Iteratively update strategies
    for _ in range(10):

        new_strategy_a = find_best_strategy(
            network,
            edge_a,
            edge_b,
            content_size,
            strategy_b,
            parameters
        )

        new_strategy_b = find_best_strategy(
            network,
            edge_b,
            edge_a,
            content_size,
            strategy_a,
            parameters
        )

        if (
            new_strategy_a == strategy_a
            and new_strategy_b == strategy_b
        ):
            break

        strategy_a = new_strategy_a
        strategy_b = new_strategy_b

    return strategy_a, strategy_b


# ============================================================
# DECIDE WHETHER TO COOPERATE
# ============================================================

def should_cooperate(
    network,
    edge_a,
    edge_b,
    content_size,
    parameters=None
):
    """
    Returns True if edge_a should cooperate with edge_b.
    """

    strategy_a, strategy_b = determine_strategies(
        network,
        edge_a,
        edge_b,
        content_size,
        parameters
    )

    return strategy_a == COOPERATE


# ============================================================
# EVALUATE ALL COOPERATIVE PAIRS
# ============================================================

def evaluate_network_cooperation(
    network,
    content_size,
    parameters=None
):
    """
    Evaluates cooperation decisions for all connected
    edge-server pairs.
    """

    decisions = {}

    edge_servers = get_edge_servers(
        network
    )

    for edge_a in edge_servers:

        cooperative_edges = get_cooperative_edges(
            network,
            edge_a
        )

        for edge_b in cooperative_edges:

            # Avoid evaluating the same pair twice
            pair = tuple(
                sorted(
                    [edge_a, edge_b]
                )
            )

            if pair in decisions:
                continue

            strategy_a, strategy_b = (
                determine_strategies(
                    network,
                    edge_a,
                    edge_b,
                    content_size,
                    parameters
                )
            )

            decisions[pair] = {
                "edge_a": edge_a,
                "edge_b": edge_b,
                "strategy_a": strategy_a,
                "strategy_b": strategy_b
            }

    return decisions


# ============================================================
# PRINT GAME RESULTS
# ============================================================

def print_game_results(decisions):
    """
    Prints the cooperation decisions.
    """

    print("\n")
    print("=" * 65)
    print("             GAME THEORY RESULTS")
    print("=" * 65)

    for pair, decision in decisions.items():

        print(
            f"{decision['edge_a']} <-> "
            f"{decision['edge_b']}"
        )

        print(
            f"  {decision['edge_a']}: "
            f"{decision['strategy_a']}"
        )

        print(
            f"  {decision['edge_b']}: "
            f"{decision['strategy_b']}"
        )

        print("-" * 65)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Build the network
    network = build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )

    # Evaluate cooperation
    decisions = evaluate_network_cooperation(
        network,
        content_size=100
    )

    # Display decisions
    print_game_results(
        decisions
    )