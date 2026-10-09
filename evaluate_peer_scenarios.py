"""Reproduce a controlled link-quality sensitivity experiment (no policy edits)."""
import hashlib
import json
import random
import statistics
from pathlib import Path
from topology import build_edge_network
from simulation import run_simulation, get_simulation_summary, DATA_SOURCE, CONTENT

STRATEGIES = ['non_cooperative', 'always_cooperative', 'cooperative', 'ml_cooperative']
SCENARIOS = ['fast', 'slow', 'mixed']
SEEDS = list(range(10))
REQUESTS = 1000
FAST = {'latency': 2.0, 'bandwidth': 1000.0}
SLOW = {'latency': 40.0, 'bandwidth': 50.0}


def network_for(seed, scenario):
    g = build_edge_network(edges_per_region=3, users_per_region=6, cache_capacity=3, seed=seed)
    # One of three links in each regional triangle is fast in the mixed case.
    # A separate RNG rotates its identity without changing request generation.
    rng = random.Random(10000 + seed)
    regions = sorted({d['region'] for _, d in g.nodes(data=True) if d.get('type') == 'edge'})
    for region in regions:
        links = sorted((a, b) for a, b, d in g.edges(data=True)
                       if d.get('link_type') == 'cooperative' and g.nodes[a]['region'] == region)
        fast_index = rng.randrange(len(links))
        for i, (a, b) in enumerate(links):
            config = FAST if scenario == 'fast' or (scenario == 'mixed' and i == fast_index) else SLOW
            g.edges[a, b].update(config)
    return g


def main():
    out = Path(__file__).parent / 'evaluation_results'
    out.mkdir(exist_ok=True)
    runs = []
    reference_traces = {}
    for seed in SEEDS:
        for scenario in SCENARIOS:
            for strategy in STRATEGIES:
                g = network_for(seed, scenario)
                results = run_simulation(g, num_requests=REQUESTS, strategy=strategy, seed=seed)
                trace = [(r['user'], r['content']) for r in results]
                digest = hashlib.sha256(json.dumps(trace).encode()).hexdigest()
                reference_traces.setdefault(seed, digest)
                assert digest == reference_traces[seed], 'Unequal evaluation workloads'
                record = dict(seed=seed, scenario=scenario, strategy=strategy,
                              request_trace_sha256=digest, **get_simulation_summary(results))
                runs.append(record)
            print(f'Completed seed {seed}, {scenario}', flush=True)
        (out/'raw_results.json').write_text(json.dumps(runs, indent=2))
    metrics = ['overall_hit_rate', 'average_latency', 'total_bandwidth_used', 'origin_requests',
               'local_hits', 'cooperative_hits', 'total_peer_checks', 'average_coordination_latency_ms']
    summary = []
    for scenario in SCENARIOS:
        for strategy in STRATEGIES:
            rows = [r for r in runs if r['scenario'] == scenario and r['strategy'] == strategy]
            summary.append(dict(scenario=scenario, strategy=strategy, **{
                metric: {'mean': statistics.mean(r[metric] for r in rows),
                         'sample_sd': statistics.stdev(r[metric] for r in rows)}
                for metric in metrics}))
    paired = []
    for scenario in SCENARIOS:
        for comparator in ['always_cooperative', 'non_cooperative']:
            changes = []
            for seed in SEEDS:
                base = next(r for r in runs if (r['seed'],r['scenario'],r['strategy']) == (seed,scenario,comparator))
                game = next(r for r in runs if (r['seed'],r['scenario'],r['strategy']) == (seed,scenario,'cooperative'))
                changes.append({'latency_reduction_pct': 100*(base['average_latency']-game['average_latency'])/base['average_latency'],
                                'hit_rate_gain_pp': game['overall_hit_rate']-base['overall_hit_rate'],
                                'traffic_reduction_pct':100*(base['total_bandwidth_used']-game['total_bandwidth_used'])/base['total_bandwidth_used'],
                                'origin_request_difference':game['origin_requests']-base['origin_requests']})
            paired.append(dict(scenario=scenario, comparator=comparator,
                               latency_wins=sum(c['latency_reduction_pct'] > 1e-9 for c in changes),
                               latency_ties=sum(abs(c['latency_reduction_pct']) <= 1e-9 for c in changes),
                               means={k:statistics.mean(c[k] for c in changes) for k in changes[0]}))
    payload = dict(data_source=DATA_SOURCE, catalog=CONTENT, requests=REQUESTS, seeds=SEEDS,
                   edges_per_region=3, users_per_region=6, cache_capacity_items=3,
                   fast_link=FAST, slow_link=SLOW, mixed='1 fast and 2 slow links per regional triangle',
                   summary=summary, paired_comparisons=paired)
    (out/'summary.json').write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()
