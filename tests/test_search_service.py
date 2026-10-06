import unittest
from unittest.mock import Mock, patch

from src import search_service


class SearchServiceTests(unittest.TestCase):
    def setUp(self):
        search_service.app.config.update(TESTING=True)
        self.client = search_service.app.test_client()

    def test_search_matches_case_insensitively(self):
        response_from_index = Mock()
        response_from_index.raise_for_status.return_value = None
        response_from_index.json.return_value = [
            {"id": 1, "title": "Campus News", "text": "New laboratory", "name": "Uni"},
            {"id": 2, "title": "Sports", "text": "A match", "name": "Uni"},
        ]

        with patch.object(search_service.requests, "get", return_value=response_from_index):
            response = self.client.get("/search?q=LABORATORY")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.get_json()["results"]], [1])

    def test_empty_query_does_not_call_index(self):
        with patch.object(search_service.requests, "get") as get_index:
            response = self.client.get("/search?q=%20%20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])
        get_index.assert_not_called()

    def test_reports_unavailable_news_index(self):
        with patch.object(
            search_service.requests,
            "get",
            side_effect=search_service.requests.ConnectionError("offline"),
        ):
            response = self.client.get("/search?q=campus")

        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.get_json())

    def test_health_check_returns_http_200(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
