"""
demand_predictor.py

Machine learning module for content popularity prediction.

This module does NOT decide whether edge servers cooperate
(that remains game_theory.py's job). It only predicts WHICH
content is likely to be requested next at a given edge
server, so that the "ml_cooperative" strategy in
simulation.py can:

    1. Prefetch predicted-popular content into free cache
       slots before it is actually requested.
    2. Evict the item least likely to be needed again,
       instead of relying on plain LRU.

Model
-----
A RandomForestClassifier is trained on a per-edge request
history. For every historical request, one training row is
created for EVERY item in the content catalog (not just the
one requested), labelled 1 for the item that was actually
requested and 0 for the rest. Features are built only from
information available BEFORE that request happened, so the
model cannot see the future.

Note
----
The current request generator (simulation.generate_request)
samples content with the same popularity weights regardless
of region/edge, so the model mainly learns global content
popularity rather than edge-specific patterns. The features
below (frequency_so_far, recency_gap) still let it rank
"hot" vs "cold" content per edge as usage accumulates, and
the design generalizes cleanly if per-region popularity is
ever introduced.
"""

import random

import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from topology import get_users, get_user_edge


# ============================================================
# POPULARITY PREDICTOR
# ============================================================

class PopularityPredictor:
    """
    Predicts, per edge server, how likely each content item
    is to be requested next.

    Usage
    -----
    predictor = PopularityPredictor(content_catalog)
    predictor.fit(training_log)

    # during live simulation, after each real request:
    predictor.observe(edge, content, request_id)

    # to decide what to prefetch / evict:
    predictor.top_predictions(edge, request_id, top_n=1)
    predictor.least_likely(edge, request_id, candidates)
    """

    def __init__(self, content_catalog):

        self.catalog = content_catalog

        self.model = None
        self.feature_columns = None
        self.trained = False

        # Running counters used both for training feature
        # construction and for live predictions.
        # edge -> content -> count / last_request_id
        self.frequency = {}
        self.last_seen = {}

    # --------------------------------------------------------
    # BUILD FEATURE ROW(S) FOR ONE EDGE, USING CURRENT COUNTERS
    # --------------------------------------------------------

    def _rows_for_edge(self, edge, request_id):

        rows = []

        edge_frequency = self.frequency.get(edge, {})
        edge_last_seen = self.last_seen.get(edge, {})

        for content, size in self.catalog.items():

            frequency_so_far = edge_frequency.get(content, 0)

            recency_gap = (
                request_id
                - edge_last_seen.get(content, 0)
            )

            rows.append({
                "edge": edge,
                "content": content,
                "frequency_so_far": frequency_so_far,
                "recency_gap": recency_gap,
                "content_size": size
            })

        return rows

    # --------------------------------------------------------
    # UPDATE RUNNING COUNTERS AFTER A REAL REQUEST
    # --------------------------------------------------------

    def observe(self, edge, content, request_id):
        """
        Updates the running frequency/recency counters after
        a real request has been processed.

        Must be called AFTER any predictions for that
        request have already been made, so features never
        leak future information.
        """

        self.frequency.setdefault(edge, {})
        self.last_seen.setdefault(edge, {})

        self.frequency[edge][content] = (
            self.frequency[edge].get(content, 0) + 1
        )

        self.last_seen[edge][content] = request_id

    # --------------------------------------------------------
    # TRAIN THE MODEL
    # --------------------------------------------------------

    def fit(self, request_log):
        """
        Trains the popularity model from a historical
        request log.

        Parameters
        ----------
        request_log : list of dict
            Each entry must contain "edge", "content" and
            "request_id", in chronological order.
        """

        training_rows = []

        # Local counters replayed from scratch so training
        # features only ever see the past.
        frequency = {}
        last_seen = {}

        for entry in request_log:

            edge = entry["edge"]
            actual_content = entry["content"]
            request_id = entry["request_id"]

            frequency.setdefault(edge, {})
            last_seen.setdefault(edge, {})

            for content, size in self.catalog.items():

                frequency_so_far = frequency[edge].get(
                    content, 0
                )

                recency_gap = (
                    request_id
                    - last_seen[edge].get(content, 0)
                )

                training_rows.append({
                    "edge": edge,
                    "content": content,
                    "frequency_so_far": frequency_so_far,
                    "recency_gap": recency_gap,
                    "content_size": size,
                    "label": (
                        1 if content == actual_content else 0
                    )
                })

            frequency[edge][actual_content] = (
                frequency[edge].get(actual_content, 0) + 1
            )

            last_seen[edge][actual_content] = request_id

        data = pd.DataFrame(training_rows)

        features = pd.get_dummies(
            data[
                [
                    "edge",
                    "content",
                    "frequency_so_far",
                    "recency_gap",
                    "content_size"
                ]
            ],
            columns=["edge", "content"]
        )

        self.feature_columns = features.columns

        labels = data["label"]

        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            random_state=42
        )

        self.model.fit(features, labels)

        self.trained = True

        # Live counters continue on from the training log,
        # so predictions right after training already reflect
        # the full history seen so far.
        self.frequency = frequency
        self.last_seen = last_seen

    # --------------------------------------------------------
    # PREDICT SCORES FOR EVERY CONTENT ITEM AT ONE EDGE
    # --------------------------------------------------------

    def predict_scores(self, edge, request_id):
        """
        Returns a dict {content: probability_of_next_request}
        for the given edge, using the current running
        counters.
        """

        if not self.trained:
            return {
                content: 0.0
                for content in self.catalog
            }

        rows = self._rows_for_edge(edge, request_id)
        data = pd.DataFrame(rows)

        features = pd.get_dummies(
            data[
                [
                    "edge",
                    "content",
                    "frequency_so_far",
                    "recency_gap",
                    "content_size"
                ]
            ],
            columns=["edge", "content"]
        )

        # Align columns with training-time feature set
        # (unseen edges/content at prediction time simply
        # get zero-filled indicator columns).
        features = features.reindex(
            columns=self.feature_columns,
            fill_value=0
        )

        if len(self.model.classes_) > 1:
            probabilities = self.model.predict_proba(
                features
            )[:, 1]
        else:
            probabilities = [0.0] * len(data)

        return dict(
            zip(data["content"], probabilities)
        )

    # --------------------------------------------------------
    # TOP-N PREDICTED CONTENT (FOR PREFETCHING)
    # --------------------------------------------------------

    def top_predictions(self, edge, request_id, top_n=1):
        """
        Returns the top_n content items most likely to be
        requested next at the given edge.
        """

        scores = self.predict_scores(edge, request_id)

        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True
        )

        return [
            content
            for content, _ in ranked[:top_n]
        ]

    # --------------------------------------------------------
    # LEAST LIKELY CANDIDATE (FOR EVICTION)
    # --------------------------------------------------------

    def least_likely(self, edge, request_id, candidates):
        """
        Given a set of currently cached content items,
        returns the one predicted least likely to be
        requested again. Returns None if candidates is empty.
        """

        candidates = list(candidates)

        if not candidates:
            return None

        scores = self.predict_scores(edge, request_id)

        return min(
            candidates,
            key=lambda content: scores.get(content, 0.0)
        )


# ============================================================
# GENERATE A TRAINING REQUEST LOG
# ============================================================

def generate_training_log(
    network,
    content_catalog,
    popularity_weights,
    num_requests=200,
    seed=1
):
    """
    Generates a synthetic historical request log used to
    train the PopularityPredictor before the real simulation
    starts.

    This mirrors simulation.generate_request()'s weighted
    random sampling, but is kept self-contained here to avoid
    a circular import with simulation.py (simulation.py
    imports PopularityPredictor from this module).

    Parameters
    ----------
    network : networkx.Graph
        The network topology (already built).

    content_catalog : dict
        Content name -> size in MB.

    popularity_weights : list
        Relative popularity weight per content item, in the
        same order as content_catalog.

    num_requests : int
        Number of synthetic training requests to generate.

    seed : int
        Random seed, kept independent from the seed used for
        the real evaluation run so the two request sequences
        don't overlap.

    Returns
    -------
    list of dict
        Chronological request log with request_id, user,
        edge, region and content for each entry.
    """

    rng = random.Random(seed)

    users = get_users(network)
    contents = list(content_catalog.keys())

    log = []

    for request_id in range(1, num_requests + 1):

        user = rng.choice(users)

        content = rng.choices(
            contents,
            weights=popularity_weights,
            k=1
        )[0]

        edge = get_user_edge(network, user)
        region = network.nodes[edge]["region"]

        log.append({
            "request_id": request_id,
            "user": user,
            "edge": edge,
            "region": region,
            "content": content
        })

    return log
