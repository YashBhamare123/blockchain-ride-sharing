from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client() -> TestClient:
    app = create_app(init_db=False)
    return TestClient(app)


def test_pricing_estimate_without_tip_or_ceiling() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/pricing/estimate",
            json={
                "distanceMeters": 5000,
                "durationSeconds": 900,
                "ceilingEnabled": False,
            },
        )
        body = response.json()
        assert response.status_code == 200
        assert body["baseFareWei"] > 0
        assert body["serviceFeeWei"] >= 0
        assert body["tipWei"] == 0
        assert body["ceilingBondWei"] == 0
        assert body["requiredMsgValueWei"] == body["baseFareWei"]


def test_pricing_estimate_with_fixed_tip() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/pricing/estimate",
            json={
                "distanceMeters": 3000,
                "durationSeconds": 600,
                "tipType": "fixed",
                "tipValue": 100000000000000,
                "ceilingEnabled": False,
            },
        )
        body = response.json()
        assert response.status_code == 200
        assert body["tipWei"] == 100000000000000
        assert body["estimatedTotalWei"] == body["baseFareWei"] + body["serviceFeeWei"] + body["tipWei"]


def test_pricing_estimate_with_percent_tip_and_ceiling() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/pricing/estimate",
            json={
                "distanceMeters": 7000,
                "durationSeconds": 1200,
                "tipType": "percent",
                "tipValue": 10,
                "ceilingEnabled": True,
            },
        )
        body = response.json()
        assert response.status_code == 200
        assert body["tipWei"] > 0
        assert body["ceilingBondWei"] > 0
        assert body["requiredMsgValueWei"] == body["baseFareWei"] + body["ceilingBondWei"]
