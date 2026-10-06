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
            1: {"views": 5, "likes": 2, "comments": 3},
            2: {"views": 12, "likes": 1, "comments": 4},
        }
        with (
            patch.object(site, "get_connection", return_value=nullcontext(connection)),
            patch.object(site, "get_post_stats", return_value=(stats, True)),
        ):
            response = self.client.get("/statistics")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"12", response.data)
        self.assertIn(b"17", response.data)
        self.assertIn(b"<strong>7</strong>", response.data)
        self.assertLess(response.data.index(b"Second story"), response.data.index(b"First story"))

    def test_statistics_page_shows_only_ten_most_popular_posts(self):
        rows = [
            (post_id, f"Story {post_id}", "University", f"{post_id:02d}.10.26")
            for post_id in range(1, 13)
        ]
        stats = {
            post_id: {"views": post_id, "likes": 0, "comments": 0}
            for post_id in range(1, 13)
        }
        connection = self.connection_with_rows(rows)
        with (
            patch.object(site, "get_connection", return_value=nullcontext(connection)),
            patch.object(site, "get_post_stats", return_value=(stats, True)),
        ):
            response = self.client.get("/statistics")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertEqual(html.count("<tr>"), 11)
        self.assertIn("Story 12", html)
        self.assertIn("Story 3", html)
        self.assertNotIn("<th scope=\"row\">Story 2</th>", html)
        self.assertNotIn("<th scope=\"row\">Story 1</th>", html)
        self.assertIn("<strong>78</strong>", html)
        self.assertIn("<strong>12</strong>", html)

    def test_homepage_stays_online_when_database_is_unavailable(self):
        with patch.object(site, "get_connection", side_effect=RuntimeError("database down")):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Статистика временно недоступна".encode(), response.data)
        self.assertIn("Последние события".encode(), response.data)

    def test_homepage_prioritizes_newest_articles_by_date(self):
        rows = [
            (1, "Old story", "Old body", "University A", "01.10.26"),
            (2, "Newest story", "Newest body", "University B", "15.10.26"),
        ]
        connection = self.connection_with_rows(rows)
        with (
            patch.object(site, "get_connection", return_value=nullcontext(connection)),
            patch.object(site, "get_post_stats", return_value=({}, True)),
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertLess(html.index("Newest story"), html.index("Old story"))


if __name__ == "__main__":
    unittest.main()
