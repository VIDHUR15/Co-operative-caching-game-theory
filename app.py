from flask import Flask, render_template, request

from topology import build_edge_network
from simulation import run_simulation,get_simulation_summary


app = Flask(__name__)


# ---------------------------------------------------------
# Run Simulation
# ---------------------------------------------------------

def run_experiment(
    strategy,
    num_requests,
    cache_capacity=3,
    edges_per_region=2,
    users_per_region=2
):

    network = build_edge_network(
        edges_per_region=edges_per_region,
        users_per_region=users_per_region,
        cache_capacity=cache_capacity,
        seed=42
    )

    results = run_simulation(
        network,
        num_requests=num_requests,
        strategy=strategy,
        seed=42
    )

    summary = get_simulation_summary(results)

    return summary


# ---------------------------------------------------------
# Calculate Improvement
# ---------------------------------------------------------

def calculate_improvement(non_cooperative, cooperative):

    improvement = {}

    # Hit rate improvement
    if non_cooperative["overall_hit_rate"] != 0:
        improvement["hit_rate"] = (
            (
                cooperative["overall_hit_rate"]
                - non_cooperative["overall_hit_rate"]
            )
            / non_cooperative["overall_hit_rate"]
        ) * 100
    else:
        improvement["hit_rate"] = 0

    # Latency reduction
    if non_cooperative["average_latency"] != 0:
        improvement["latency"] = (
            (
                non_cooperative["average_latency"]
                - cooperative["average_latency"]
            )
            / non_cooperative["average_latency"]
        ) * 100
    else:
        improvement["latency"] = 0

    # Bandwidth reduction
    if non_cooperative["total_bandwidth_used"] != 0:
        improvement["bandwidth"] = (
            (
                non_cooperative["total_bandwidth_used"]
                - cooperative["total_bandwidth_used"]
            )
            / non_cooperative["total_bandwidth_used"]
        ) * 100
    else:
        improvement["bandwidth"] = 0

    # Origin load reduction
    if non_cooperative["origin_requests"] != 0:
        improvement["origin_load"] = (
            (
                non_cooperative["origin_requests"]
                - cooperative["origin_requests"]
            )
            / non_cooperative["origin_requests"]
        ) * 100
    else:
        improvement["origin_load"] = 0

    return improvement


# ---------------------------------------------------------
# Prepare Graph Data
# ---------------------------------------------------------

def prepare_graph_data(non_cooperative, always_cooperative, cooperative, ml_cooperative):

    labels = [
        "Non-Cooperative",
        "Always-Cooperative",
        "Game-Theoretic",
        "ML Cooperative"
    ]

    graph_data = {

        "hit_rate": {
            "labels": labels,
            "values": [
                non_cooperative["overall_hit_rate"],
                always_cooperative["overall_hit_rate"],
                cooperative["overall_hit_rate"],
                ml_cooperative["overall_hit_rate"]
            ]
        },

        "latency": {
            "labels": labels,
            "values": [
                non_cooperative["average_latency"],
                always_cooperative["average_latency"],
                cooperative["average_latency"],
                ml_cooperative["average_latency"]
            ]
        },

        "bandwidth": {
            "labels": labels,
            "values": [
                non_cooperative["total_bandwidth_used"],
                always_cooperative["total_bandwidth_used"],
                cooperative["total_bandwidth_used"],
                ml_cooperative["total_bandwidth_used"]
            ]
        },

        "origin_load": {
            "labels": labels,
            "values": [
                non_cooperative["origin_requests"],
                always_cooperative["origin_requests"],
                cooperative["origin_requests"],
                ml_cooperative["origin_requests"]
            ]
        },

        "cache_hits": {
            "labels": labels,
            "local": [
                non_cooperative["local_hits"],
                always_cooperative["local_hits"],
                cooperative["local_hits"],
                ml_cooperative["local_hits"]
            ],
            "cooperative": [
                non_cooperative["cooperative_hits"],
                always_cooperative["cooperative_hits"],
                cooperative["cooperative_hits"],
                ml_cooperative["cooperative_hits"]
            ]
        }
    }

    return graph_data


# ---------------------------------------------------------
# Home Page
# ---------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def index():

    # Default values
    num_requests = 100
    cache_capacity = 3
    edges_per_region = 2
    users_per_region = 2

    always_cooperative = None
    improvement_always = None
    improvement_game_vs_always = None
    non_cooperative = None
    cooperative = None
    ml_cooperative = None
    improvement = None
    improvement_ml = None
    graph_data = None

    # Run simulation when button is pressed
    if request.method == "POST":

        def read_int(field, default, minimum, maximum):
            """
            Reads one integer form field, falling back to the
            default if missing/invalid, and clamping into a
            sane range so a bad value can't produce a broken
            or enormous simulation.
            """

            try:
                value = int(request.form.get(field, default))
            except (TypeError, ValueError):
                return default

            return max(minimum, min(maximum, value))

        num_requests = read_int(
            "num_requests", 100, 1, 20000
        )

        cache_capacity = read_int(
            "cache_capacity", 3, 1, 50
        )

        edges_per_region = read_int(
            "edges_per_region", 2, 2, 6
        )

        users_per_region = read_int(
            "users_per_region", 2, 1, 20
        )

        # Run all four simulations on the same seeded workload
        non_cooperative = run_experiment(
            "non_cooperative",
            num_requests,
            cache_capacity,
            edges_per_region,
            users_per_region
        )

        always_cooperative = run_experiment(
            "always_cooperative",
            num_requests,
            cache_capacity,
            edges_per_region,
            users_per_region
        )

        cooperative = run_experiment(
            "cooperative",
            num_requests,
            cache_capacity,
            edges_per_region,
            users_per_region
        )

        ml_cooperative = run_experiment(
            "ml_cooperative",
            num_requests,
            cache_capacity,
            edges_per_region,
            users_per_region
        )

        # Calculate improvements (each cooperative variant
        # compared against the non-cooperative baseline)
        improvement = calculate_improvement(
            non_cooperative,
            cooperative
        )

        improvement_ml = calculate_improvement(
            non_cooperative,
            ml_cooperative
        )

        improvement_always = calculate_improvement(non_cooperative, always_cooperative)
        improvement_game_vs_always = calculate_improvement(always_cooperative, cooperative)

        # Prepare graph information
        graph_data = prepare_graph_data(
            non_cooperative,
            always_cooperative,
            cooperative,
            ml_cooperative
        )

    # Send everything to index.html
    return render_template(
        "index.html",

        num_requests=num_requests,

        cache_capacity=cache_capacity,

        edges_per_region=edges_per_region,

        users_per_region=users_per_region,

        non_cooperative=non_cooperative,
        always_cooperative=always_cooperative,
        improvement_always=improvement_always,
        improvement_game_vs_always=improvement_game_vs_always,

        cooperative=cooperative,

        ml_cooperative=ml_cooperative,

        improvement=improvement,

        improvement_ml=improvement_ml,

        graph_data=graph_data
    )


# ---------------------------------------------------------
# Run Flask Application
# ---------------------------------------------------------

if __name__ == "__main__":

    import os

    # Debug mode (auto-reload, interactive tracebacks) is
    # off by default. Enable it locally with:
    #   FLASK_DEBUG=1 python app.py
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=" * 60)
    print("   COOPERATIVE CACHING SIMULATION")
    print("=" * 60)

    print("\nStarting web application...")
    print("Open your browser at:")
    print("http://127.0.0.1:5000")

    if debug_mode:
        print("(debug mode ON - set FLASK_DEBUG=0 to disable)")

    app.run(
        debug=debug_mode,
        host="127.0.0.1",
        port=5000
    )