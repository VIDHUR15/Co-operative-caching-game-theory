import matplotlib.pyplot as plt

from topology import build_edge_network
from simulation import run_simulation,get_simulation_summary


# ---------------------------------------------------------
# Run one experiment
# ---------------------------------------------------------

def run_experiment(strategy, num_requests=100, seed=42):

    network = build_edge_network(
        edges_per_region=2,
        users_per_region=2,
        cache_capacity=3,
        seed=seed
    )

    results = run_simulation(
    network,
    num_requests=num_requests,
    strategy=strategy,
    seed=seed
)

    summary = get_simulation_summary(results)

    return summary


# ---------------------------------------------------------
# Compare strategies
# ---------------------------------------------------------

def compare_strategies(num_requests=100, seed=42):

    print("\nRunning non-cooperative simulation...")

    non_cooperative = run_experiment(
        "non_cooperative",
        num_requests,
        seed
    )

    print("Running always-cooperative simulation...")
    always_cooperative = run_experiment("always_cooperative", num_requests, seed)

    print("Running cooperative simulation...")

    cooperative = run_experiment(
        "cooperative",
        num_requests,
        seed
    )

    print("Running ML-cooperative simulation...")

    ml_cooperative = run_experiment(
        "ml_cooperative",
        num_requests,
        seed
    )

    return non_cooperative, always_cooperative, cooperative, ml_cooperative


# ---------------------------------------------------------
# Calculate improvement
# ---------------------------------------------------------

def calculate_improvement(non_cooperative, cooperative):

    improvement = {}

    old = non_cooperative
    new = cooperative

    # Hit rate
    if old["overall_hit_rate"] != 0:
        improvement["hit_rate"] = (
            (new["overall_hit_rate"] -
             old["overall_hit_rate"])
            / old["overall_hit_rate"]
        ) * 100
    else:
        improvement["hit_rate"] = 0

    # Latency
    if old["average_latency"] != 0:
        improvement["latency"] = (
            (old["average_latency"] -
             new["average_latency"])
            / old["average_latency"]
        ) * 100
    else:
        improvement["latency"] = 0

    # Bandwidth
    if old["total_bandwidth_used"] != 0:
        improvement["bandwidth"] = (
            (old["total_bandwidth_used"] -
             new["total_bandwidth_used"])
            / old["total_bandwidth_used"]
        ) * 100
    else:
        improvement["bandwidth"] = 0

    # Origin load
    if old["origin_requests"] != 0:
        improvement["origin_load"] = (
            (old["origin_requests"] -
             new["origin_requests"])
            / old["origin_requests"]
        ) * 100
    else:
        improvement["origin_load"] = 0

    return improvement


# ---------------------------------------------------------
# Print results
# ---------------------------------------------------------

def print_results(
    non_cooperative,
    always_cooperative,
    cooperative,
    ml_cooperative,
    improvement,
    improvement_ml
):

    print("\n")
    print("=" * 115)
    print("          COOPERATIVE CACHING PERFORMANCE")
    print("=" * 115)

    print(
        f"{'Metric':<30}"
        f"{'Non-Cooperative':<20}"
        f"{'Always-Cooperative':<20}"
        f"{'Game-Theoretic':<20}"
        f"{'ML Cooperative':<20}"
    )

    print("-" * 115)

    print(
        f"{'Total Requests':<30}"
        f"{non_cooperative['total_requests']:<20}"
        f"{always_cooperative['total_requests']:<20}"
        f"{cooperative['total_requests']:<20}"
        f"{ml_cooperative['total_requests']:<20}"
    )

    print(
        f"{'Local Cache Hits':<30}"
        f"{non_cooperative['local_hits']:<20}"
        f"{always_cooperative['local_hits']:<20}"
        f"{cooperative['local_hits']:<20}"
        f"{ml_cooperative['local_hits']:<20}"
    )

    print(
        f"{'Cooperative Cache Hits':<30}"
        f"{non_cooperative['cooperative_hits']:<20}"
        f"{always_cooperative['cooperative_hits']:<20}"
        f"{cooperative['cooperative_hits']:<20}"
        f"{ml_cooperative['cooperative_hits']:<20}"
    )

    print(
        f"{'Origin Requests':<30}"
        f"{non_cooperative['origin_requests']:<20}"
        f"{always_cooperative['origin_requests']:<20}"
        f"{cooperative['origin_requests']:<20}"
        f"{ml_cooperative['origin_requests']:<20}"
    )

    print(
        f"{'Overall Hit Rate (%)':<30}"
        f"{non_cooperative['overall_hit_rate']:<20.2f}"
        f"{always_cooperative['overall_hit_rate']:<20.2f}"
        f"{cooperative['overall_hit_rate']:<20.2f}"
        f"{ml_cooperative['overall_hit_rate']:<20.2f}"
    )

    print(
        f"{'Average Latency (ms)':<30}"
        f"{non_cooperative['average_latency']:<20.2f}"
        f"{always_cooperative['average_latency']:<20.2f}"
        f"{cooperative['average_latency']:<20.2f}"
        f"{ml_cooperative['average_latency']:<20.2f}"
    )

    print(
        f"{'Bandwidth Used (MB)':<30}"
        f"{non_cooperative['total_bandwidth_used']:<20.2f}"
        f"{always_cooperative['total_bandwidth_used']:<20.2f}"
        f"{cooperative['total_bandwidth_used']:<20.2f}"
        f"{ml_cooperative['total_bandwidth_used']:<20.2f}"
    )

    print("-" * 115)

    for label, key in [("Prefetch origin accesses", "prefetch_origin_requests"),
                       ("Demand origin misses", "demand_origin_requests"),
                       ("Peer checks", "total_peer_checks"),
                       ("Avg coordination cost (ms)", "average_coordination_latency_ms")]:
        print(f"{label:<30}" + "".join(
            f"{summary[key]:<20.2f}" for summary in
            [non_cooperative, always_cooperative, cooperative, ml_cooperative]
        ))

    print("\nIMPROVEMENT: COOPERATIVE (GAME THEORY) vs NON-COOPERATIVE")
    print("-" * 55)

    print(f"Hit Rate Improvement  : {improvement['hit_rate']:.2f}%")
    print(f"Latency Reduction     : {improvement['latency']:.2f}%")
    print(f"Bandwidth Reduction   : {improvement['bandwidth']:.2f}%")
    print(f"Origin Load Reduction : {improvement['origin_load']:.2f}%")

    print("\nIMPROVEMENT: ML COOPERATIVE vs NON-COOPERATIVE")
    print("-" * 55)

    print(f"Hit Rate Improvement  : {improvement_ml['hit_rate']:.2f}%")
    print(f"Latency Reduction     : {improvement_ml['latency']:.2f}%")
    print(f"Bandwidth Reduction   : {improvement_ml['bandwidth']:.2f}%")
    print(f"Origin Load Reduction : {improvement_ml['origin_load']:.2f}%")

    for label, baseline, candidate in [
        ("ALWAYS-COOPERATIVE vs NON-COOPERATIVE", non_cooperative, always_cooperative),
        ("GAME-THEORETIC vs ALWAYS-COOPERATIVE", always_cooperative, cooperative),
    ]:
        changes = calculate_improvement(baseline, candidate)
        print(f"\nIMPROVEMENT: {label}")
        for metric, value in changes.items():
            print(f"{metric:<22}: {value:.2f}%")
    print("=" * 115)


# ---------------------------------------------------------
# Graph 1: Cache Hit Rate
# ---------------------------------------------------------

def plot_hit_rate(non_cooperative, always_cooperative, cooperative, ml_cooperative):

    strategies = [
        "Non-Cooperative",
        "Always-Cooperative",
        "Game-Theoretic",
        "ML Cooperative"
    ]

    values = [
        non_cooperative["overall_hit_rate"],
        always_cooperative["overall_hit_rate"],
        cooperative["overall_hit_rate"],
        ml_cooperative["overall_hit_rate"]
    ]

    plt.figure(figsize=(10, 5))

    plt.bar(
        strategies,
        values,
        color=["#64748b", "#14b8a6", "#3b82f6", "#f59e0b"]
    )

    plt.title("Cache Hit Rate Comparison")
    plt.ylabel("Hit Rate (%)")
    plt.xlabel("Caching Strategy")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------
# Graph 2: Average Latency
# ---------------------------------------------------------

def plot_latency(non_cooperative, always_cooperative, cooperative, ml_cooperative):

    strategies = [
        "Non-Cooperative",
        "Always-Cooperative",
        "Game-Theoretic",
        "ML Cooperative"
    ]

    values = [
        non_cooperative["average_latency"],
        always_cooperative["average_latency"],
        cooperative["average_latency"],
        ml_cooperative["average_latency"]
    ]

    plt.figure(figsize=(10, 5))

    plt.bar(
        strategies,
        values,
        color=["#64748b", "#14b8a6", "#8b5cf6", "#f59e0b"]
    )

    plt.title("Average Network Latency")
    plt.ylabel("Latency (ms)")
    plt.xlabel("Caching Strategy")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------
# Graph 3: Bandwidth Usage
# ---------------------------------------------------------

def plot_bandwidth(non_cooperative, always_cooperative, cooperative, ml_cooperative):

    strategies = [
        "Non-Cooperative",
        "Always-Cooperative",
        "Game-Theoretic",
        "ML Cooperative"
    ]

    values = [
        non_cooperative["total_bandwidth_used"],
        always_cooperative["total_bandwidth_used"],
        cooperative["total_bandwidth_used"],
        ml_cooperative["total_bandwidth_used"]
    ]

    plt.figure(figsize=(10, 5))

    plt.bar(
        strategies,
        values,
        color=["#64748b", "#14b8a6", "#06b6d4", "#f59e0b"]
    )

    plt.title("Total Bandwidth Usage")
    plt.ylabel("Bandwidth Used (MB)")
    plt.xlabel("Caching Strategy")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------
# Graph 4: Origin Server Load
# ---------------------------------------------------------

def plot_origin_load(non_cooperative, always_cooperative, cooperative, ml_cooperative):

    strategies = [
        "Non-Cooperative",
        "Always-Cooperative",
        "Game-Theoretic",
        "ML Cooperative"
    ]

    values = [
        non_cooperative["origin_requests"],
        always_cooperative["origin_requests"],
        cooperative["origin_requests"],
        ml_cooperative["origin_requests"]
    ]

    plt.figure(figsize=(10, 5))

    plt.bar(
        strategies,
        values,
        color=["#64748b", "#14b8a6", "#22c55e", "#f59e0b"]
    )

    plt.title("Origin Server Load")
    plt.ylabel("Number of Origin Requests")
    plt.xlabel("Caching Strategy")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------
# Graph 5: Cache Hit Distribution
# ---------------------------------------------------------

def plot_cache_hits(non_cooperative, always_cooperative, cooperative, ml_cooperative):

    strategies = [
        "Non-Cooperative",
        "Always-Cooperative",
        "Game-Theoretic",
        "ML Cooperative"
    ]

    local_hits = [
        non_cooperative["local_hits"],
        always_cooperative["local_hits"],
        cooperative["local_hits"],
        ml_cooperative["local_hits"]
    ]

    cooperative_hits = [
        non_cooperative["cooperative_hits"],
        always_cooperative["cooperative_hits"],
        cooperative["cooperative_hits"],
        ml_cooperative["cooperative_hits"]
    ]

    plt.figure(figsize=(10, 5))

    x = range(len(strategies))

    plt.bar(
        x,
        local_hits,
        label="Local Cache Hits"
    )

    plt.bar(
        x,
        cooperative_hits,
        bottom=local_hits,
        label="Cooperative Cache Hits"
    )

    plt.xticks(x, strategies)

    plt.title("Cache Hit Distribution")
    plt.ylabel("Number of Requests")
    plt.xlabel("Caching Strategy")

    plt.legend()

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    NUM_REQUESTS = 100
    SEED = 42

    # Run experiments
    non_cooperative, always_cooperative, cooperative, ml_cooperative = (
        compare_strategies(
            NUM_REQUESTS,
            SEED
        )
    )

    # Calculate improvement (each cooperative variant vs the
    # non-cooperative baseline)
    improvement = calculate_improvement(
        non_cooperative,
        cooperative
    )

    improvement_ml = calculate_improvement(
        non_cooperative,
        ml_cooperative
    )

    # Display numerical results
    print_results(
        non_cooperative,
        always_cooperative,
        cooperative,
        ml_cooperative,
        improvement,
        improvement_ml
    )

    # Display graphs
    plot_hit_rate(
        non_cooperative,
        always_cooperative,
        cooperative,
        ml_cooperative
    )

    plot_latency(
        non_cooperative,
        always_cooperative,
        cooperative,
        ml_cooperative
    )

    plot_bandwidth(
        non_cooperative,
        always_cooperative,
        cooperative,
        ml_cooperative
    )

    plot_origin_load(
        non_cooperative,
        always_cooperative,
        cooperative,
        ml_cooperative
    )

    plot_cache_hits(
        non_cooperative,
        always_cooperative,
        cooperative,
        ml_cooperative
    )


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------

if __name__ == "__main__":
    main()