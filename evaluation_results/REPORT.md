> Historical synthetic-video evaluation. These results predate removal of that catalog; they are not Wikipedia results.

# Peer-link sensitivity evaluation

120 runs: 4 strategies × 3 scenarios × 10 seeds (0–9), with 1,000 requests per run. Four regions, 3 edges and 6 users per region; cache capacity 3 items; caches start empty. ML uses its existing 200-request generated training history. The bundled five-item synthetic video catalog is used. These are controlled simulations, not real-network measurements.

Only cooperative link latency and bandwidth change between scenarios. Fast: 2 ms and 1,000 Mbps. Slow: 40 ms and 50 Mbps. Mixed: one fast and two slow links in each region’s three-edge triangle, with fast-link identity rotated using an independent seeded RNG. Origin, regional, and user links remain as generated for each seed. Every strategy and scenario uses exactly the same user/content request sequence for a given seed; hashes are stored in raw_results.json.

## Results

Values are mean ± sample standard deviation across 10 seeds. Traffic is total payload MB across links per 1,000-request run. Origin requests include demand and prefetch accesses. Latency is modeled end-to-end delivery time, including peer coordination and synchronous prefetch costs; it is not time to first byte.

### Fast peer links

| Strategy | Hit rate (%) | Avg latency (ms) | Traffic (MB) | Origin requests | Peer checks |
|---|---:|---:|---:|---:|---:|
| Non-cooperative | 69.10 ± 1.76 | 40944.67 ± 2475.53 | 451570.00 ± 21239.22 | 309.00 ± 17.56 | 0.00 ± 0.00 |
| Always-cooperative | 91.83 ± 0.43 | 38922.90 ± 2475.20 | 378870.00 ± 15826.42 | 81.70 ± 4.35 | 462.20 ± 28.36 |
| Game-theoretic | 91.83 ± 0.43 | 38922.90 ± 2475.20 | 378870.00 ± 15826.42 | 81.70 ± 4.35 | 462.20 ± 28.36 |
| ML-cooperative | 90.44 ± 1.09 | 39357.60 ± 2604.98 | 399245.00 ± 21654.43 | 106.20 ± 9.30 | 397.20 ± 27.04 |

### Slow peer links

| Strategy | Hit rate (%) | Avg latency (ms) | Traffic (MB) | Origin requests | Peer checks |
|---|---:|---:|---:|---:|---:|
| Non-cooperative | 69.10 ± 1.76 | 40944.67 ± 2475.53 | 451570.00 ± 21239.22 | 309.00 ± 17.56 | 0.00 ± 0.00 |
| Always-cooperative | 91.83 ± 0.43 | 50035.61 ± 2637.40 | 378870.00 ± 15826.42 | 81.70 ± 4.35 | 462.20 ± 28.36 |
| Game-theoretic | 69.10 ± 1.76 | 40944.67 ± 2475.53 | 451570.00 ± 21239.22 | 309.00 ± 17.56 | 0.00 ± 0.00 |
| ML-cooperative | 73.56 ± 2.70 | 41176.35 ± 2614.16 | 464690.00 ± 25039.61 | 275.00 ± 28.53 | 0.00 ± 0.00 |

### Mixed peer links

| Strategy | Hit rate (%) | Avg latency (ms) | Traffic (MB) | Origin requests | Peer checks |
|---|---:|---:|---:|---:|---:|
| Non-cooperative | 69.10 ± 1.76 | 40944.67 ± 2475.53 | 451570.00 ± 21239.22 | 309.00 ± 17.56 | 0.00 ± 0.00 |
| Always-cooperative | 91.83 ± 0.43 | 46068.27 ± 3031.61 | 378870.00 ± 15826.42 | 81.70 ± 4.35 | 462.20 ± 28.36 |
| Game-theoretic | 79.89 ± 1.31 | 40101.80 ± 2498.26 | 421880.00 ± 20060.00 | 201.10 ± 13.05 | 212.40 ± 16.41 |
| ML-cooperative | 81.69 ± 1.64 | 40395.67 ± 2625.18 | 437020.00 ± 26060.48 | 193.70 ± 16.17 | 175.30 ± 24.70 |

## Paired game-theoretic comparisons

Percentage changes are calculated within each seed and then averaged. Positive reduction means lower latency or traffic; positive origin-request difference means more requests to origin.

| Scenario | Compared with | Latency reduction (%) | Hit-rate gain (pp) | Traffic reduction (%) | Origin-request difference | Latency wins/ties/losses |
|---|---|---:|---:|---:|---:|---|
| fast | Always-cooperative | 0.00 | 0.00 | 0.00 | 0.00 | 0/10/0 |
| fast | Non-cooperative | 4.95 | 22.73 | 16.08 | -227.30 | 10/0/0 |
| slow | Always-cooperative | 18.19 | -22.73 | -19.17 | 227.30 | 10/0/0 |
| slow | Non-cooperative | 0.00 | 0.00 | 0.00 | 0.00 | 0/10/0 |
| mixed | Always-cooperative | 12.92 | -11.94 | -11.33 | 119.40 | 10/0/0 |
| mixed | Non-cooperative | 2.07 | 10.79 | 6.57 | -107.90 | 10/0/0 |

## Interpretation limits

- This evaluates the corrected ML accounting and timeline. Payoff equations and the ML model are unchanged; payoff actions are explicitly route preferences, not sharing permissions.
- The game-theoretic strategy includes both payoff filtering and cost-ranked peer selection; an advantage over first-available sharing cannot isolate game theory from ordinary cost-aware routing.
- ML prefetch transfers are charged to latency, traffic, and origin access. Just-in-time prefetches are misses, and model timestamps continue after training. No background overlap is modeled.
- Peer overhead uses the existing modeled constant (10 ms plus a peer round trip); control-message bytes, queueing and concurrent bandwidth contention are not modeled.
- The five synthetic objects and fixed popularity distribution limit generalization. A higher hit rate need not imply lower latency, especially on slow peer links.
- Scenarios deliberately span contrasting link quality. They are sensitivity checks, not evidence of deployment-wide superiority or global optimality.

## Reproduce

From the project directory, run `python evaluate_peer_scenarios.py`. Raw per-seed metrics and the machine-readable summary are in this directory.
