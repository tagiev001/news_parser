import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from src import app as site


class SiteAppTests(unittest.TestCase):
    def setUp(self):
        site.app.config.update(TESTING=True)
        self.client = site.app.test_client()

    @staticmethod
    def connection_with_rows(rows):
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = rows
        return connection

    def test_homepage_renders_active_articles_and_root_templates(self):
        rows = [
            (2, "Second story", "Second body", "University B", "02.10.26"),
            (1, "First story", "First body", "University A", "01.10.26"),
        ]
        connection = self.connection_with_rows(rows)
        with (
            patch.object(site, "get_connection", return_value=nullcontext(connection)),
            patch.object(site, "get_post_stats", return_value=({}, False)),
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"First story", response.data)
        self.assertIn(b"Second story", response.data)
        self.assertNotIn(b"Deleted story", response.data)
        self.assertIn("Статистика временно недоступна".encode(), response.data)

    def test_load_articles_returns_json_and_pagination_metadata(self):
        connection = self.connection_with_rows([
            (2, "Second story", "Second body", "University B", "02.10.26"),
            (1, "First story", "First body", "University A", "01.10.26"),
        ])
        with (
            patch.object(site, "get_connection", return_value=nullcontext(connection)),
            patch.object(site, "get_post_stats", return_value=({}, True)),
        ):
            response = self.client.get("/load_articles?offset=0&limit=1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual([row["id"] for row in payload["articles"]], [2])
        self.assertTrue(payload["has_more"])

    def test_static_assets_remain_available_after_source_move(self):
        response = self.client.get("/static/main.css")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b".news-grid", response.data)
        finally:
            response.close()

    def test_statistics_page_displays_totals_and_ranking(self):
        connection = self.connection_with_rows([
            (1, "First story", "University A", "01.10.26"),
            (2, "Second story", "University B", "02.10.26"),
        ])
        stats = {
            1: {"views": 5, "likes": 2},
            2: {"views": 12, "likes": 1},
        }
        with (
            patch.object(site, "get_connection", return_value=nullcontext(connection)),
            patch.object(site, "get_post_stats", return_value=(stats, True)),
        ):
            response = self.client.get("/statistics")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"12", response.data)
        self.assertIn(b"17", response.data)
        self.assertLess(response.data.index(b"Second story"), response.data.index(b"First story"))


if __name__ == "__main__":
    unittest.main()
