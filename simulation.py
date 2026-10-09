import csv
import math
import os
import random
from game_theory import should_cooperate, calculate_cooperation_cost

from topology import (
    build_edge_network,
    get_edge_servers,
    get_users,
    get_user_edge,
    get_cooperative_edges,
    add_to_cache,
    touch_cache,
    get_link_info,
    calculate_transfer_time
)

from demand_predictor import (
    PopularityPredictor,
    generate_training_log
)


# ============================================================
# CONTENT CATALOG
# ============================================================
#
# Requires the Wikimedia CSV. Missing or invalid data is never replaced
# by a fabricated content catalog.
_REAL_DATASET_PATH = os.path.join(os.path.dirname(__file__), "data", "wikipedia_content_catalog.csv")


def _load_content_catalog():
    """Read a validated Wikipedia catalog; fail clearly rather than substitute data."""
    instruction = "Run: python data/fetch_wikipedia_dataset.py"
    content, weights = {}, []
    try:
        with open(_REAL_DATASET_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not {"article", "size_mb", "views"}.issubset(reader.fieldnames or []):
                raise ValueError("Required CSV columns: article, size_mb, views")
            for line, row in enumerate(reader, start=2):
                article = row["article"].strip()
                size, views = float(row["size_mb"]), float(row["views"])
                if not article or article in content:
                    raise ValueError(f"Empty or duplicate article on row {line}")
                if not all(math.isfinite(v) and v > 0 for v in (size, views)):
                    raise ValueError(f"Size and views must be finite and positive on row {line}")
                content[article] = size
                weights.append(views)
        if not content:
            raise ValueError("The CSV has no articles")
    except (OSError, ValueError, TypeError, AttributeError, csv.Error) as exc:
        raise RuntimeError(
            f"Wikipedia dataset missing or invalid: {_REAL_DATASET_PATH}. "
            f"{instruction}. Details: {exc}"
        ) from exc
    return content, weights, f"Wikimedia pageview catalog ({len(content)} articles)"


CONTENT, CONTENT_POPULARITY_WEIGHTS, DATA_SOURCE = _load_content_catalog()


# ============================================================
# TRANSFER TIME
# ============================================================

# ============================================================
# TRANSFER TIME
# ============================================================
#
# calculate_transfer_time() now lives in topology.py, shared
# with game_theory.py so both modules use identical, real
# transfer-time math instead of two disconnected models.


# ============================================================
# LOCAL CACHE REQUEST
# ============================================================

def handle_local_cache_hit(
    network,
    user,
    edge,
    content
):
    """
    Handles a request when content exists
    in the user's connected edge server.
    """

    content_size = CONTENT[content]

    link = get_link_info(
        network,
        user,
        edge
    )

    latency = calculate_transfer_time(
        content_size,
        link["bandwidth"],
        link["latency"]
    )

    # A hit counts as "recently used" for LRU purposes.
    touch_cache(network, edge, content)

    return {
        "result": "local_hit",
        "source": edge,
        "latency": latency,
        "bandwidth_used": content_size
    }


# ============================================================
# COOPERATIVE CACHE REQUEST
# ============================================================

def handle_cooperative_request(
    network, user, edge, content, peer, predictor=None, request_id=None
):
    """Transfer from exactly one selected peer; never search other peers.

    Peer lookup/coordination latency is charged by process_request, including
    unsuccessful lookups. This helper accounts only for payload delivery.
    """
    if peer not in get_cooperative_edges(network, edge):
        raise ValueError(f"{peer} is not a connected cooperative peer of {edge}")
    if content not in network.nodes[peer]["cache"]:
        return None

    content_size = CONTENT[content]
    peer_link = get_link_info(network, edge, peer)
    user_link = get_link_info(network, user, edge)
    latency = (
        calculate_transfer_time(content_size, peer_link["bandwidth"], peer_link["latency"])
        + calculate_transfer_time(content_size, user_link["bandwidth"], user_link["latency"])
    )
    touch_cache(network, peer, content)
    add_to_cache(network, edge, content, predictor=predictor, request_id=request_id)
    return {
        "result": "cooperative_hit",
        "source": peer,
        "latency": latency,
        "bandwidth_used": content_size * 2
    }


def _finish_request(result, user, edge, content, attempts=(), decisions=(), prefetch=None):
    """Charge every attempted lookup once, even when origin serves the item."""
    overhead = sum(attempt["cost_ms"] for attempt in attempts)
    result["payload_latency_ms"] = result["latency"]
    result["coordination_latency_ms"] = overhead
    prefetch = prefetch or {"content": None, "latency_ms": 0.0, "traffic_mb": 0.0, "origin_requests": 0}
    result["prefetch_latency_ms"] = prefetch["latency_ms"]
    result["prefetch_traffic_mb"] = prefetch["traffic_mb"]
    result["prefetch_origin_requests"] = prefetch["origin_requests"]
    result["prefetched_content"] = prefetch["content"]
    result["prefetch_satisfied_current"] = prefetch["content"] == content
    # A just-in-time fetch is a cold demand miss, not a free cache hit.
    if result["prefetch_satisfied_current"]:
        result["result"] = "origin_request"
        result["source"] = "Origin"
    result["latency"] += overhead + prefetch["latency_ms"]
    result["bandwidth_used"] += prefetch["traffic_mb"]
    result["peer_checks"] = len(attempts)
    result["peer_attempts"] = list(attempts)
    result["peer_decisions"] = list(decisions)
    result.update(user=user, edge=edge, content=content)
    return result


# ============================================================
# ORIGIN REQUEST
# ============================================================

def handle_origin_request(
    network,
    user,
    edge,
    content,
    predictor=None,
    request_id=None
):
    """
    Handles a request when content is unavailable
    in local and cooperative caches.

    Request path:

        User -> Edge -> Region -> Origin
    """

    content_size = CONTENT[content]

    region = network.nodes[
        edge
    ]["region"]

    # --------------------------------------------------------
    # User -> Edge
    # --------------------------------------------------------

    user_link = get_link_info(
        network,
        user,
        edge
    )

    user_latency = calculate_transfer_time(
        content_size,
        user_link["bandwidth"],
        user_link["latency"]
    )

    # --------------------------------------------------------
    # Edge -> Region
    # --------------------------------------------------------

    edge_region_link = get_link_info(
        network,
        edge,
        region
    )

    edge_region_latency = calculate_transfer_time(
        content_size,
        edge_region_link["bandwidth"],
        edge_region_link["latency"]
    )

    # --------------------------------------------------------
    # Region -> Origin
    # --------------------------------------------------------

    origin_link = get_link_info(
        network,
        region,
        "Origin"
    )

    origin_latency = calculate_transfer_time(
        content_size,
        origin_link["bandwidth"],
        origin_link["latency"]
    )

    total_latency = (
        user_latency +
        edge_region_latency +
        origin_latency
    )

    # Cache content at edge
    add_to_cache(
        network,
        edge,
        content,
        predictor=predictor,
        request_id=request_id
    )

    return {
        "result": "origin_request",
        "source": "Origin",
        "latency": total_latency,
        "bandwidth_used": content_size * 3
    }


# ============================================================
# PROCESS ONE REQUEST
# ============================================================

def process_request(
    network,
    user,
    content,
    strategy="cooperative",
    predictor=None,
    request_id=None
):
    """
    Processes one content request.

    Strategies: non_cooperative, always_cooperative, cooperative,
    ml_cooperative. Always-cooperative uses ordinary LRU and bypasses
    game-theoretic decisions; it still checks the local cache first.

    Request priority:

        1. ML prefetch (ml_cooperative strategy only)
        2. Local cache
        3. Cooperative cache
        4. Origin server

    Parameters
    ----------
    predictor : demand_predictor.PopularityPredictor, optional
        Trained popularity model. Only used when
        strategy == "ml_cooperative".

    request_id : int, optional
        Current request number. Required alongside
        `predictor` for prefetching/eviction decisions.
    """

    edge = get_user_edge(
        network,
        user
    )

    if edge is None:
        raise ValueError(
            f"No edge server connected to {user}"
        )

    # --------------------------------------------------------
    # 0. ML-GUIDED PREFETCH (synchronous origin-to-edge transfer)
    # --------------------------------------------------------
    #
    # Before handling this request, opportunistically cache
    # the content predicted most likely to be needed next at
    # this edge - but ONLY if there is free space. This never
    # evicts existing cached content on a guess, it just fills
    # otherwise-idle cache slots ahead of time.

    prefetch = None

    if (
        strategy == "ml_cooperative"
        and predictor is not None
        and request_id is not None
    ):

        cache = network.nodes[edge]["cache"]
        capacity = network.graph["cache_capacity"]

        if len(cache) < capacity:

            for predicted_content in predictor.top_predictions(
                edge,
                request_id,
                top_n=1
            ):

                if predicted_content not in cache:

                    region = network.nodes[edge]["region"]
                    size = CONTENT[predicted_content]
                    links = [get_link_info(network, "Origin", region),
                             get_link_info(network, region, edge)]
                    prefetch = {
                        "content": predicted_content,
                        "latency_ms": sum(calculate_transfer_time(size, link["bandwidth"], link["latency"]) for link in links),
                        "traffic_mb": size * 2,
                        "origin_requests": 1,
                    }
                    add_to_cache(
                        network,
                        edge,
                        predicted_content,
                        predictor=predictor,
                        request_id=request_id
                    )

    # --------------------------------------------------------
    # 1. LOCAL CACHE
    # --------------------------------------------------------

    if content in network.nodes[
        edge
    ]["cache"]:

        result = handle_local_cache_hit(
            network,
            user,
            edge,
            content
        )

        return _finish_request(result, user, edge, content, prefetch=prefetch)

    attempts = []
    decisions = []
    if strategy in ("always_cooperative", "cooperative", "ml_cooperative"):
        peers = get_cooperative_edges(network, edge)
        if strategy != "always_cooperative":
            # Link attributes are known topology metadata. Rank by the full
            # per-peer route estimate, without looking inside peer caches.
            def route_cost(peer):
                link = get_link_info(network, edge, peer)
                return (
                    calculate_transfer_time(CONTENT[content], link["bandwidth"], link["latency"])
                    + calculate_cooperation_cost(network, edge, peer, CONTENT[content])
                )
            peers = sorted(peers, key=lambda peer: (route_cost(peer), peer))

        for peer in peers:
            approved = (strategy == "always_cooperative" or
                        should_cooperate(network, edge, peer, CONTENT[content]))
            decisions.append({"peer": peer, "approved": approved})
            if not approved:
                # A local decision from known link metadata sends no query.
                continue

            cost = calculate_cooperation_cost(network, edge, peer, CONTENT[content])
            result = handle_cooperative_request(
                network, user, edge, content, peer=peer,
                predictor=predictor, request_id=request_id
            )
            attempts.append({"peer": peer, "cost_ms": cost, "hit": result is not None})
            if result is not None:
                return _finish_request(result, user, edge, content, attempts, decisions, prefetch=prefetch)

    result = handle_origin_request(
        network, user, edge, content, predictor=predictor, request_id=request_id
    )
    return _finish_request(result, user, edge, content, attempts, decisions, prefetch=prefetch)


# ============================================================
# GENERATE RANDOM REQUEST
# ============================================================

def generate_request(
    users,
    content_catalog
):
    """
    Generates one random user content request.

    Popularity weights make some content more
    frequently requested.
    """

    user = random.choice(users)

    contents = list(
        content_catalog.keys()
    )

    content = random.choices(
        contents,
        weights=CONTENT_POPULARITY_WEIGHTS,
        k=1
    )[0]

    return user, content


# ============================================================
# RUN SIMULATION
# ============================================================

def run_simulation(
    network,
    num_requests=100,
    strategy="cooperative",
    seed=42,
    training_requests=200
):
    """
    Runs the CDN simulation.

    Parameters
    ----------
    training_requests : int
        Only used when strategy == "ml_cooperative". Number
        of synthetic requests used to pre-train the
        popularity predictor before the timed/evaluated run
        starts. Generated with an independent random stream
        so it does not reuse the evaluation random stream. Repeated
        user/content pairs can still occur naturally.

    Returns
    -------
    results : list
        Results for every request.
    """

    predictor = None
    history_end = 0

    if strategy == "ml_cooperative":

        training_log = generate_training_log(
            network,
            CONTENT,
            CONTENT_POPULARITY_WEIGHTS,
            num_requests=training_requests,
            seed=seed + 1000
        )

        predictor = PopularityPredictor(CONTENT)
        predictor.fit(training_log)
        history_end = max(entry["request_id"] for entry in training_log)

    random.seed(seed)

    users = get_users(
        network
    )

    results = []

    for request_number in range(
        1,
        num_requests + 1
    ):

        user, content = generate_request(
            users,
            CONTENT
        )

        model_request_id = history_end + request_number

        result = process_request(
            network,
            user,
            content,
            strategy,
            predictor=predictor,
            request_id=model_request_id
        )

        result["model_request_id"] = model_request_id
        result["request_id"] = (
            request_number
        )

        results.append(
            result
        )

        # Keep the predictor's counters current so later
        # predictions in this same run reflect everything
        # seen so far, including this request.
        if predictor is not None:

            edge = result["edge"]

            predictor.observe(
                edge,
                content,
                model_request_id
            )

    return results


# ============================================================
# SIMULATION SUMMARY
# ============================================================

def get_simulation_summary(results):
    """
    Calculates basic simulation statistics.

    Returns
    -------
    dict
        Summary statistics.
    """

    total_requests = len(results)

    local_hits = sum(
        result["result"] == "local_hit"
        for result in results
    )

    cooperative_hits = sum(
        result["result"] == "cooperative_hit"
        for result in results
    )

    demand_origin_requests = sum(
        result["result"] == "origin_request"
        for result in results
    )

    prefetch_origin_requests = sum(r.get("prefetch_origin_requests", 0) for r in results)
    demand_fetch_origin_requests = sum(
        r["result"] == "origin_request" and not r.get("prefetch_satisfied_current", False)
        for r in results
    )
    origin_requests = demand_fetch_origin_requests + prefetch_origin_requests

    total_latency = sum(
        result["latency"]
        for result in results
    )

    total_bandwidth = sum(
        result["bandwidth_used"]
        for result in results
    )

    if total_requests > 0:

        local_hit_rate = (
            local_hits /
            total_requests
        ) * 100

        cooperative_hit_rate = (
            cooperative_hits /
            total_requests
        ) * 100

        overall_hit_rate = (
            (local_hits + cooperative_hits) /
            total_requests
        ) * 100

        origin_request_rate = (
            demand_origin_requests /
            total_requests
        ) * 100

        average_latency = (
            total_latency /
            total_requests
        )

    else:

        local_hit_rate = 0
        cooperative_hit_rate = 0
        overall_hit_rate = 0
        origin_request_rate = 0
        average_latency = 0

    return {
        "total_requests": total_requests,
        "local_hits": local_hits,
        "cooperative_hits": cooperative_hits,
        "origin_requests": origin_requests,
        "demand_origin_requests": demand_origin_requests,
        "demand_fetch_origin_requests": demand_fetch_origin_requests,
        "prefetch_origin_requests": prefetch_origin_requests,
        "total_prefetch_latency_ms": sum(r.get("prefetch_latency_ms", 0) for r in results),
        "total_prefetch_traffic_mb": sum(r.get("prefetch_traffic_mb", 0) for r in results),

        "local_hit_rate": local_hit_rate,
        "cooperative_hit_rate": cooperative_hit_rate,
        "overall_hit_rate": overall_hit_rate,
        "origin_request_rate": origin_request_rate,

        "average_latency": average_latency,

        "total_bandwidth_used": total_bandwidth,
        "total_coordination_latency_ms": sum(r.get("coordination_latency_ms", 0) for r in results),
        "average_coordination_latency_ms": (
            sum(r.get("coordination_latency_ms", 0) for r in results) / total_requests
            if total_requests else 0
        ),
        "total_peer_checks": sum(r.get("peer_checks", 0) for r in results)
    }


# ============================================================
# PRINT RESULTS
# ============================================================

def print_simulation_summary(summary):
    """
    Prints simulation statistics.
    """

    print("\n")
    print("=" * 55)
    print("              SIMULATION RESULTS")
    print("=" * 55)

    print(
        f"Total Requests          : "
        f"{summary['total_requests']}"
    )

    print(
        f"Local Cache Hits        : "
        f"{summary['local_hits']}"
    )

    print(
        f"Cooperative Cache Hits  : "
        f"{summary['cooperative_hits']}"
    )

    print(
        f"Origin Requests         : "
        f"{summary['origin_requests']}"
    )

    print("-" * 55)

    print(
        f"Local Hit Rate          : "
        f"{summary['local_hit_rate']:.2f}%"
    )

    print(
        f"Cooperative Hit Rate    : "
        f"{summary['cooperative_hit_rate']:.2f}%"
    )

    print(
        f"Overall Cache Hit Rate  : "
        f"{summary['overall_hit_rate']:.2f}%"
    )

    print(
        f"Origin Request Rate     : "
        f"{summary['origin_request_rate']:.2f}%"
    )

    print(
        f"Average Latency         : "
        f"{summary['average_latency']:.2f} ms"
    )

    print(
        f"Total Bandwidth Used    : "
        f"{summary['total_bandwidth_used']:.2f} MB"
    )

    print("=" * 55)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(f"Content catalog source: {DATA_SOURCE}\n")

    # Create topology
    network = build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )

    # Run simulation
    results = run_simulation(
        network,
        num_requests=100,
        seed=42
    )

    # Generate summary
    summary = get_simulation_summary(
        results
    )

    # Display results
    print_simulation_summary(
        summary
    )