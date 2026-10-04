import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from src import comments_service


class CommentsServiceTests(unittest.TestCase):
    def setUp(self):
        comments_service.app.config.update(TESTING=True)
        self.client = comments_service.app.test_client()

    def test_creates_and_lists_comments(self):
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = (
            1, "Alex", "Hello!", "2026-10-05T00:00:00+00:00"
        )
        with patch.object(
            comments_service, "get_connection", return_value=nullcontext(connection)
        ):
            created = self.client.post(
                "/posts/7/comments",
                json={"nick": "  Alex  ", "text": "  Hello!  "},
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["comment"]["nick"], "Alex")
        self.assertEqual(created.get_json()["comment"]["text"], "Hello!")

        connection.execute.return_value.fetchall.return_value = [
            (1, "Alex", "Hello!", "2026-10-05T00:00:00+00:00")
        ]
        with patch.object(
            comments_service, "get_connection", return_value=nullcontext(connection)
        ):
            listed = self.client.get("/posts/7/comments")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["comments"]), 1)

    def test_rejects_invalid_comment_payload(self):
        response = self.client.post(
            "/posts/7/comments",
            json={"nick": " ", "text": "empty nick"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
