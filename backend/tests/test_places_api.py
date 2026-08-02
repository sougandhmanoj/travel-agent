from fastapi.testclient import TestClient


def test_search_returns_ranked_city_and_hub_details(client: TestClient) -> None:
    response = client.get("/api/v1/places/search", params={"q": "goa"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "goa"
    assert payload["results"][0] == {
        "place_id": "hub_00001",
        "name": "Goa International Airport",
        "place_type": "airport",
        "locality_or_city": "Dabolim",
        "state": "Goa",
        "code": "GOI",
        "latitude": 15.3805865,
        "longitude": 73.8326572,
    }


def test_search_rejects_missing_or_blank_query(client: TestClient) -> None:
    assert client.get("/api/v1/places/search").status_code == 422
    assert client.get("/api/v1/places/search", params={"q": "   "}).status_code == 422
