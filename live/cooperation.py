"""
cooperation.py

Decides whether an edge node should ask a peer for content
instead of going to the origin - using the exact same
grounded formula as game_theory.py's calculate_payoff():

    benefit = time saved vs going to the origin
    cost    = one real round-trip to the peer + a small
              fixed coordination overhead
    cooperate if benefit - cost (+ a small tiebreaker for
    mutual cooperation) > defecting (which pays 0)

The difference from game_theory.py: benefit and cost are
computed from REAL measured round-trip times to the actual
peer and origin processes (see ping()), not from a simulated
network link. This is a related retrieval heuristic, not the same equilibrium rule.
"""

import time

import requests


# Same defaults as game_theory.py's DEFAULT_PARAMETERS,
# kept identical on purpose so the live system and the
# simulation are directly comparable.
COORDINATION_OVERHEAD_MS = 10.0
MUTUAL_COOPERATION_BONUS_MS = 2.0


def ping(base_url, samples=3, timeout=2.0):
    """
    Measures REAL round-trip time to another node's /health
    endpoint, in milliseconds. Returns None if unreachable.
    """

    times = []

    for _ in range(samples):
        start = time.perf_counter()

        try:
            response = requests.get(
                f"{base_url}/health",
                timeout=timeout
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            continue

        elapsed_ms = (time.perf_counter() - start) * 1000
        times.append(elapsed_ms)

    if not times:
        return None

    return sum(times) / len(times)


def estimate_transfer_ms(size_mb, latency_ms, bandwidth_mbps):
    """
    Same transfer-time formula as topology.py's
    calculate_transfer_time(), for consistency with the
    simulation. Used when real bandwidth isn't separately
    measurable (see note in should_cooperate()).
    """

    content_megabits = size_mb * 8
    transmission_ms = (content_megabits / bandwidth_mbps) * 1000
    return latency_ms + transmission_ms


def should_cooperate(
    peer_latency_ms,
    origin_latency_ms,
    content_size_mb,
    assumed_peer_bandwidth_mbps=200,
    assumed_origin_bandwidth_mbps=50
):
    """
    Live retrieval heuristic using measured RTT and assumed bandwidth.

    Parameters
    ----------
    peer_latency_ms : float
        REAL measured round-trip time to the cooperative peer.

    origin_latency_ms : float
        REAL measured round-trip time to the origin.

    content_size_mb : float
        Real size of the requested content.

    assumed_peer_bandwidth_mbps, assumed_origin_bandwidth_mbps : float
        A live process can measure round-trip latency cheaply
        (a ping), but measuring true available bandwidth needs
        a real data transfer, so these are assumed rather than
        measured. They're deliberately DIFFERENT (peer faster
        than origin by default) because a cooperative peer is
        typically on the same LAN/datacenter, while the origin
        is typically reached over the wider internet - using
        the SAME assumed bandwidth for both would make
        content_size cancel out of the benefit calculation
        entirely (an earlier bug in this file: benefit reduced
        to just the latency difference, regardless of size).
        Latency is real and measured either way, which is what
        actually varies request-to-request.

    Returns
    -------
    bool
    """

    peer_transfer_ms = estimate_transfer_ms(
        content_size_mb, peer_latency_ms, assumed_peer_bandwidth_mbps
    )

    origin_transfer_ms = estimate_transfer_ms(
        content_size_mb, origin_latency_ms, assumed_origin_bandwidth_mbps
    )

    benefit = origin_transfer_ms - peer_transfer_ms

    cost = (2 * peer_latency_ms) + COORDINATION_OVERHEAD_MS

    mutual_cooperate_payoff = MUTUAL_COOPERATION_BONUS_MS + benefit - cost
    unilateral_cooperate_payoff = benefit - cost

    # Unlike the simulator's pairwise best responses, this live heuristic
    # requires a positive route benefit even without the mutual-preference
    # bonus. The peer's permission to serve is not controlled by this choice.
    return (
        mutual_cooperate_payoff > 0
        and unilateral_cooperate_payoff > 0
    )
