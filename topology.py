import networkx as nx
import random
import math
from collections import OrderedDict


# ============================================================
# NETWORK CONFIGURATION
# ============================================================

DEFAULT_REGIONS = [
    "US-East",
    "US-West",
    "Europe",
    "Asia"
]


# ============================================================
# GEOGRAPHY
# ============================================================
#
# Approximate real-world (latitude, longitude) coordinates
# for each default region's PoP, plus the origin server.
# Used to derive link bandwidth/latency from actual distance
# instead of picking randomly from a fixed list - farther
# apart = higher latency + lower bandwidth, same as a real
# CDN would experience.

REGION_COORDINATES = {
    "US-East": (38.9, -77.0),     # Washington DC / Ashburn area
    "US-West": (37.7, -122.4),    # San Francisco Bay Area
    "Europe": (51.5, -0.1),       # London
    "Asia": (1.35, 103.8)         # Singapore
}

# Origin datacenter - placed near a common real-world CDN
# origin hub (Ashburn, VA - "Data Center Alley").
ORIGIN_COORDINATE = (39.04, -77.49)


def haversine_distance(coord_a, coord_b):
    """
    Great-circle distance between two (lat, lon) points, in
    kilometers.
    """

    R = 6371.0  # Earth's radius in km

    lat1, lon1 = (
        math.radians(coord_a[0]),
        math.radians(coord_a[1])
    )

    lat2, lon2 = (
        math.radians(coord_b[0]),
        math.radians(coord_b[1])
    )

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(d_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return R * c


def distance_to_latency(distance_km, base_latency, ms_per_km):
    """
    Converts a distance into a link latency in milliseconds.

    base_latency accounts for fixed overhead (routing,
    switching) that exists even at zero distance.
    """

    return base_latency + (distance_km * ms_per_km)


def distance_to_bandwidth(
    distance_km,
    min_bandwidth,
    max_bandwidth,
    decay_km
):
    """
    Converts a distance into a link bandwidth in Mbps.

    Bandwidth decays exponentially with distance towards
    min_bandwidth, and approaches max_bandwidth as distance
    approaches zero. decay_km controls how quickly it falls
    off - a larger decay_km means bandwidth stays high over
    longer distances.
    """

    decay_factor = math.exp(-distance_km / decay_km)

    return (
        min_bandwidth
        + (max_bandwidth - min_bandwidth) * decay_factor
    )


def jitter_coordinate(base_coord, max_radius_km, rng=None):
    """
    Returns a coordinate offset from base_coord by a random
    distance/direction, up to max_radius_km.

    Used to give individual edge servers and users their own
    position within a region's metro area (real servers
    within the same city aren't all in the exact same spot),
    while staying reproducible under a fixed random seed.
    """

    if rng is None:
        rng = random

    angle = rng.uniform(0, 2 * math.pi)
    radius_km = rng.uniform(0, max_radius_km)

    lat, lon = base_coord

    # Approximate degrees-per-km (good enough at metro scale)
    d_lat = (radius_km * math.cos(angle)) / 111.0

    d_lon = (
        (radius_km * math.sin(angle))
        / (111.0 * math.cos(math.radians(lat)) + 1e-9)
    )

    return (lat + d_lat, lon + d_lon)


def get_region_coordinate(region):
    """
    Returns a (lat, lon) for the given region name.

    Falls back to a deterministic pseudo-coordinate (derived
    from the region name) for custom region lists that aren't
    in REGION_COORDINATES, so build_edge_network() never
    breaks on a non-default `regions` argument.
    """

    if region in REGION_COORDINATES:
        return REGION_COORDINATES[region]

    # Deterministic fallback spread across the globe based on
    # the region name's hash, so custom regions still get a
    # stable, distinct coordinate.
    seed_value = sum(ord(c) for c in region)

    lat = -60 + (seed_value % 120)
    lon = -180 + ((seed_value * 7) % 360)

    return (lat, lon)


# ============================================================
# BUILD COMPLETE EDGE/CDN NETWORK
# ============================================================

def build_edge_network(
    regions=None,
    edges_per_region=2,
    users_per_region=2,
    cache_capacity=3,
    seed=42
):
    """
    Creates an edge/CDN network topology.

    Network structure:

                    Origin
                       |
                Regional PoPs
                       |
                 Edge Servers
                    /     \
                 Users   Users

    Edge servers within the same region are connected
    through cooperative links.

    Parameters
    ----------
    regions : list
        List of geographical regions.

    edges_per_region : int
        Number of edge servers in each region.

    users_per_region : int
        Number of users in each region.

    cache_capacity : int
        Maximum number of content items an edge server
        can store.

    seed : int
        Random seed for reproducible topology generation.

    Returns
    -------
    G : networkx.Graph
        Complete edge network topology.
    """

    if regions is None:
        regions = DEFAULT_REGIONS.copy()

    if users_per_region < edges_per_region:
        import warnings

        warnings.warn(
            f"users_per_region ({users_per_region}) is less "
            f"than edges_per_region ({edges_per_region}): "
            f"{edges_per_region - users_per_region} edge "
            f"server(s) per region will have no users, so "
            f"they never cache anything and can never serve "
            f"a cooperative hit. Raise users_per_region to "
            f"at least edges_per_region for the extra edges "
            f"to affect results.",
            stacklevel=2
        )

    random.seed(seed)

    G = nx.Graph()

    # Store global topology information
    G.graph["network_type"] = "CDN/Edge Network"
    G.graph["regions"] = regions
    G.graph["cache_capacity"] = cache_capacity

    # --------------------------------------------------------
    # Add network components
    # --------------------------------------------------------

    add_origin(G)

    add_regions(
        G,
        regions
    )

    edge_servers = add_edge_servers(
        G,
        regions,
        edges_per_region,
        cache_capacity
    )

    add_cooperative_links(
        G,
        edge_servers
    )

    users = add_users(
        G,
        regions,
        edge_servers,
        users_per_region
    )

    return G


# ============================================================
# ORIGIN SERVER
# ============================================================

def add_origin(G):
    """
    Adds the central origin/content server.
    """

    G.add_node(
        "Origin",
        type="origin",
        region="central",
        coordinate=ORIGIN_COORDINATE
    )


# ============================================================
# REGIONAL POPs
# ============================================================

def add_regions(G, regions):
    """
    Adds regional Points of Presence (PoPs).

    Each PoP represents a regional aggregation point
    connecting the origin to edge servers.

    Origin-region link latency/bandwidth are derived from
    the great-circle distance between the origin and the
    region, instead of being picked randomly - farther
    regions genuinely get worse links, closer regions get
    better ones.
    """

    for region in regions:

        coordinate = get_region_coordinate(region)

        G.add_node(
            region,
            type="region",
            region=region,
            coordinate=coordinate
        )

        distance_km = haversine_distance(
            ORIGIN_COORDINATE,
            coordinate
        )

        # Origin -> Regional PoP
        G.add_edge(
            "Origin",
            region,

            latency=round(
                distance_to_latency(
                    distance_km,
                    base_latency=5,
                    ms_per_km=0.01
                ),
                1
            ),

            bandwidth=round(
                distance_to_bandwidth(
                    distance_km,
                    min_bandwidth=500,
                    max_bandwidth=2000,
                    decay_km=6000
                )
            ),

            link_type="origin-region",

            distance_km=round(distance_km)
        )


# ============================================================
# EDGE SERVERS
# ============================================================

def add_edge_servers(
    G,
    regions,
    edges_per_region,
    cache_capacity
):
    """
    Creates edge servers inside every regional PoP.

    Returns
    -------
    edge_servers : dict
        Dictionary containing edge servers grouped
        by region.
    """

    edge_servers = {}

    for region in regions:

        edge_servers[region] = []

        for i in range(edges_per_region):

            server_name = (
                f"Edge-{region}-{i + 1}"
            )

            region_coordinate = G.nodes[region]["coordinate"]

            # Edge servers sit somewhere within ~15km of the
            # regional PoP's coordinate (a metro area, not a
            # single point).
            edge_coordinate = jitter_coordinate(
                region_coordinate,
                max_radius_km=15
            )

            G.add_node(
                server_name,

                type="edge",

                region=region,

                coordinate=edge_coordinate,

                # Cache-related information
                cache_capacity=cache_capacity,

                # OrderedDict used as an ordered set so that
                # recency of use can be tracked (needed for
                # real LRU eviction and for touch_cache()).
                cache=OrderedDict()
            )

            distance_km = haversine_distance(
                region_coordinate,
                edge_coordinate
            )

            # Regional PoP -> Edge Server
            G.add_edge(
                region,
                server_name,

                latency=round(
                    distance_to_latency(
                        distance_km,
                        base_latency=3,
                        ms_per_km=1.0
                    ),
                    1
                ),

                bandwidth=round(
                    distance_to_bandwidth(
                        distance_km,
                        min_bandwidth=100,
                        max_bandwidth=500,
                        decay_km=10
                    )
                ),

                link_type="region-edge",

                distance_km=round(distance_km, 1)
            )

            edge_servers[region].append(
                server_name
            )

    return edge_servers


# ============================================================
# COOPERATIVE EDGE LINKS
# ============================================================

def add_cooperative_links(
    G,
    edge_servers
):
    """
    Creates links between edge servers in the same region.

    These links represent cooperative caching communication.

    Each cooperative link contains:

        latency
        bandwidth
        link_type
        cooperation
    """

    for region, servers in edge_servers.items():

        for i in range(len(servers)):

            for j in range(i + 1, len(servers)):

                server_a = servers[i]
                server_b = servers[j]

                distance_km = haversine_distance(
                    G.nodes[server_a]["coordinate"],
                    G.nodes[server_b]["coordinate"]
                )

                G.add_edge(
                    server_a,
                    server_b,

                    latency=round(
                        distance_to_latency(
                            distance_km,
                            base_latency=2,
                            ms_per_km=0.4
                        ),
                        1
                    ),

                    # Same-region peer link - short-haul and
                    # fast, unlike the long-haul link to the
                    # origin. Derived from actual distance
                    # between the two edges now, rather than
                    # picked randomly from [200, 500, 1000].
                    bandwidth=round(
                        distance_to_bandwidth(
                            distance_km,
                            min_bandwidth=200,
                            max_bandwidth=1000,
                            decay_km=10
                        )
                    ),

                    link_type="cooperative",

                    cooperation=True,

                    distance_km=round(distance_km, 1)
                )


# ============================================================
# USERS
# ============================================================
def add_to_cache(
    network,
    edge,
    content,
    predictor=None,
    request_id=None
):
    """
    Adds content to an edge server cache.

    Eviction policy
    ----------------
    - Default (predictor=None): true Least Recently Used
      (LRU) eviction. The cache is an OrderedDict, so the
      item at the front is always the least recently used.
    - ML-guided (predictor given): the item predicted least
      likely to be requested again (via
      predictor.least_likely()) is evicted instead of the
      plain LRU choice. This is used by the "ml_cooperative"
      strategy in simulation.py.

    Parameters
    ----------
    predictor : demand_predictor.PopularityPredictor, optional
        Trained popularity model used to make a smarter
        eviction choice.

    request_id : int, optional
        Current request number, required by the predictor
        to compute recency-based features.
    """

    cache = network.nodes[edge]["cache"]
    capacity = network.graph["cache_capacity"]

    if content in cache:
        # Already cached - accessing it counts as use.
        cache.move_to_end(content)
        return

    if len(cache) >= capacity:

        evict = None

        if predictor is not None and request_id is not None:
            evict = predictor.least_likely(
                edge,
                request_id,
                cache.keys()
            )

        if evict is None:
            # Fall back to plain LRU: the first key inserted
            # is the least recently used one.
            evict = next(iter(cache))

        del cache[evict]

    cache[content] = True


def touch_cache(network, edge, content):
    """
    Marks a cached item as recently used, without adding or
    evicting anything.

    Called whenever a cache HIT occurs (local or
    cooperative), so that LRU ordering reflects reads as
    well as writes.
    """

    cache = network.nodes[edge]["cache"]

    if content in cache:
        cache.move_to_end(content)


    
def add_users(
    G,
    regions,
    edge_servers,
    users_per_region
):
    """
    Creates users and connects them to edge servers.

    Returns
    -------
    users : dict
        Dictionary containing users grouped by region.
    """

    users = {}

    for region in regions:

        users[region] = []

        servers = edge_servers[region]

        for i in range(users_per_region):

            user_name = (
                f"User-{region}-{i + 1}"
            )

            # Distribute users across edge servers,
            # round-robin.
            #
            # NOTE: if users_per_region < edges_per_region,
            # the surplus edge servers get no users at all.
            # They will never cache anything, so they can
            # never serve a cooperative hit - meaning raising
            # edges_per_region alone has NO effect on results
            # unless users_per_region is raised to match.
            # build_edge_network() warns about this.
            edge = servers[
                i % len(servers)
            ]

            # Users sit somewhere within ~10km of their
            # assigned edge server (spread around a
            # neighbourhood, not all in one spot).
            user_coordinate = jitter_coordinate(
                G.nodes[edge]["coordinate"],
                max_radius_km=10
            )

            G.add_node(
                user_name,

                type="user",

                region=region,

                coordinate=user_coordinate
            )

            distance_km = haversine_distance(
                G.nodes[edge]["coordinate"],
                user_coordinate
            )

            # User -> Edge link
            G.add_edge(
                user_name,
                edge,

                latency=round(
                    distance_to_latency(
                        distance_km,
                        base_latency=1,
                        ms_per_km=0.4
                    ),
                    1
                ),

                bandwidth=round(
                    distance_to_bandwidth(
                        distance_km,
                        min_bandwidth=20,
                        max_bandwidth=100,
                        decay_km=5
                    )
                ),

                link_type="access",

                distance_km=round(distance_km, 1)
            )

            users[region].append(
                user_name
            )

    return users


# ============================================================
# GET EDGE SERVERS
# ============================================================

def get_edge_servers(G):
    """
    Returns a list of all edge servers.
    """

    return [
        node
        for node, data in G.nodes(data=True)
        if data.get("type") == "edge"
    ]


# ============================================================
# GET USERS
# ============================================================

def get_users(G):
    """
    Returns a list of all users.
    """

    return [
        node
        for node, data in G.nodes(data=True)
        if data.get("type") == "user"
    ]


# ============================================================
# GET REGIONAL PoPs
# ============================================================

def get_regions(G):
    """
    Returns a list of all regional PoPs.
    """

    return [
        node
        for node, data in G.nodes(data=True)
        if data.get("type") == "region"
    ]


# ============================================================
# GET USER'S CONNECTED EDGE SERVER
# ============================================================

def get_user_edge(G, user):
    """
    Returns the edge server directly connected to a user.
    """

    for neighbour in G.neighbors(user):

        if G.nodes[neighbour].get("type") == "edge":
            return neighbour

    return None


# ============================================================
# GET COOPERATIVE EDGES
# ============================================================

def get_cooperative_edges(G, edge):
    """
    Returns edge servers that can cooperate with
    the specified edge server.
    """

    cooperative_edges = []

    for neighbour in G.neighbors(edge):

        if G.nodes[neighbour].get("type") != "edge":
            continue

        if G.edges[edge, neighbour].get(
            "cooperation",
            False
        ):
            cooperative_edges.append(
                neighbour
            )

    return cooperative_edges


# ============================================================
# GET LINK INFORMATION
# ============================================================

# ============================================================
# TRANSFER TIME
# ============================================================
#
# Lives here (rather than in simulation.py) so that
# game_theory.py can compute real, physically-grounded
# benefit/cost values using the exact same formula the
# simulation uses for its actual results - instead of an
# unrelated set of hand-tuned constants that need re-tuning
# every time content size or link speed changes.

def calculate_transfer_time(content_size, bandwidth, latency):
    """
    Calculates approximate data transfer time.

    Parameters
    ----------
    content_size : float
        Content size in MB.

    bandwidth : float
        Link bandwidth in Mbps.

    latency : float
        Network latency in milliseconds.

    Returns
    -------
    float
        Total transfer time in milliseconds.
    """

    # Convert MB to megabits
    content_megabits = content_size * 8

    # Transmission time in milliseconds
    transmission_time = (
        content_megabits / bandwidth
    ) * 1000

    return latency + transmission_time


def get_link_info(G, node_a, node_b):
    """
    Returns latency, bandwidth and link type
    between two connected nodes.
    """

    if not G.has_edge(node_a, node_b):
        return None

    return {
        "latency": G.edges[node_a, node_b]["latency"],
        "bandwidth": G.edges[node_a, node_b]["bandwidth"],
        "link_type": G.edges[node_a, node_b]["link_type"]
    }


# ============================================================
# PRINT NETWORK INFORMATION
# ============================================================

def print_network_info(G):
    """
    Prints a summary of the complete topology.
    """

    print("\n" + "=" * 60)
    print("EDGE/CDN NETWORK INFORMATION")
    print("=" * 60)

    print(
        "Nodes    :",
        G.number_of_nodes()
    )

    print(
        "Links    :",
        G.number_of_edges()
    )

    print(
        "Regions  :",
        len(get_regions(G))
    )

    print(
        "Edge Servers :",
        len(get_edge_servers(G))
    )

    print(
        "Users    :",
        len(get_users(G))
    )

    print("\n--- NODES ---")

    for node, data in G.nodes(data=True):

        print(
            f"{node:25} "
            f"type={data.get('type'):10} "
            f"region={data.get('region')}"
        )

    print("\n--- LINKS ---")

    for u, v, data in G.edges(data=True):

        print(
            f"{u:25} <-> {v:25} "
            f"latency={data['latency']:3} ms  "
            f"bandwidth={data['bandwidth']:4} Mbps  "
            f"type={data['link_type']}"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    network = build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=42
    )

    print_network_info(network)