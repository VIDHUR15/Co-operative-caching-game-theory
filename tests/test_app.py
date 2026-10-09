"""
Tests for app.py (the Flask dashboard).
"""

import pytest

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def test_get_index_renders_empty_state(client):
    response = client.get("/")
    assert response.status_code == 200


def test_post_runs_all_four_strategies(client):
    response = client.post("/", data={
        "num_requests": "100",
        "cache_capacity": "3",
        "edges_per_region": "2",
        "users_per_region": "2"
    })

    html = response.data.decode()

    assert response.status_code == 200
    assert "Non-Cooperative" in html
    assert "Cooperative" in html
    assert "ML Cooperative" in html
    assert "Always-Cooperative" in html
    assert "Game-Theoretic vs Always-Cooperative" in html


@pytest.mark.parametrize("bad_form", [
    {"num_requests": "not_a_number"},
    {"num_requests": "-50"},
    {"cache_capacity": ""},
    {"edges_per_region": "-5", "users_per_region": "999"},
    {},
])
def test_post_handles_bad_input_without_crashing(client, bad_form):
    response = client.post("/", data=bad_form)
    assert response.status_code == 200


def test_edges_per_region_is_clamped_to_valid_range(client):
    response = client.post("/", data={
        "num_requests": "50",
        "cache_capacity": "3",
        "edges_per_region": "999",   # above the allowed max
        "users_per_region": "999"
    })

    assert response.status_code == 200
    # Should not have silently built an enormous network -
    # the read_int() clamp should have capped this.
