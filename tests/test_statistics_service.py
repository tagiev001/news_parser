import unittest
import uuid
from contextlib import nullcontext
from unittest.mock import Mock, patch

from src import statistics_service


class StatisticsServiceTests(unittest.TestCase):
    def setUp(self):
        statistics_service.app.config.update(TESTING=True)
        self.client = statistics_service.app.test_client()
        self.voter_id = str(uuid.uuid4())

    def test_views_are_unique_per_post_and_voter(self):
        connection = Mock()
        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=(4,))),
            Mock(fetchone=Mock(return_value=(1,))),
        ]
        with patch.object(
            statistics_service, "get_connection", return_value=nullcontext(connection)
        ):
            first = self.client.post(
                "/posts/4/views",
                json={"voter_id": self.voter_id},
            )
        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=None)),
            Mock(fetchone=Mock(return_value=(1,))),
        ]
        with patch.object(
            statistics_service, "get_connection", return_value=nullcontext(connection)
        ):
            repeated = self.client.post(
                "/posts/4/views",
                json={"voter_id": self.voter_id},
            )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get_json()["viewed"])
        self.assertFalse(repeated.get_json()["viewed"])
        self.assertEqual(repeated.get_json()["views"], 1)

    def test_likes_toggle_and_stats_aggregate(self):
        connection = Mock()
        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=(4,))),
            Mock(fetchone=Mock(return_value=(1,))),
        ]
        with patch.object(
            statistics_service, "get_connection", return_value=nullcontext(connection)
        ):
            liked = self.client.post(
                "/posts/4/likes",
                json={"voter_id": self.voter_id},
            )
        self.assertEqual(liked.get_json(), {"liked": True, "likes": 1})

        connection.execute.side_effect = [
            Mock(fetchall=Mock(return_value=[])),
            Mock(fetchall=Mock(return_value=[(4, 1)])),
            Mock(fetchone=Mock(return_value=("comments",))),
            Mock(fetchall=Mock(return_value=[(4, 3)])),
        ]
        with patch.object(
            statistics_service, "get_connection", return_value=nullcontext(connection)
        ):
            stats = self.client.get("/stats?post_id=4&post_id=9")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(
            stats.get_json()["stats"],
            [
                {"post_id": 4, "views": 0, "likes": 1, "comments": 3},
                {"post_id": 9, "views": 0, "likes": 0, "comments": 0},
            ],
        )

        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=None)),
            Mock(),
            Mock(fetchone=Mock(return_value=(0,))),
        ]
        with patch.object(
            statistics_service, "get_connection", return_value=nullcontext(connection)
        ):
            unliked = self.client.post(
                "/posts/4/likes",
                json={"voter_id": self.voter_id},
            )
        self.assertEqual(unliked.get_json(), {"liked": False, "likes": 0})

    def test_stats_reports_zero_comments_before_comments_schema_exists(self):
        connection = Mock()
        connection.execute.side_effect = [
            Mock(fetchall=Mock(return_value=[])),
            Mock(fetchall=Mock(return_value=[])),
            Mock(fetchone=Mock(return_value=(None,))),
        ]
        with patch.object(
            statistics_service, "get_connection", return_value=nullcontext(connection)
        ):
            response = self.client.get("/stats?post_id=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["stats"],
            [{"post_id": 4, "views": 0, "likes": 0, "comments": 0}],
        )

    def test_rejects_invalid_voter_id(self):
        response = self.client.post(
            "/posts/4/views",
            json={"voter_id": "not-a-uuid"},
        )

        self.assertEqual(response.status_code, 400)

    def test_health_check_returns_http_200_without_database(self):
        with patch.object(statistics_service, "get_connection", side_effect=AssertionError):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
