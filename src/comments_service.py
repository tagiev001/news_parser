import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from .database import COMMENTS_SCHEMA, get_connection


app = Flask(__name__)
MAX_NICK_LENGTH = 40
MAX_COMMENT_LENGTH = 2000
SERVICE_HOST = os.environ.get("COMMENTS_SERVICE_HOST", "0.0.0.0")


@app.route("/posts/<int:post_id>/comments", methods=["GET", "POST"])
def post_comments(post_id):
    if post_id < 1:
        return jsonify(error="Post ID must be positive"), 400

    if request.method == "GET":
        with get_connection(COMMENTS_SCHEMA) as connection:
            rows = connection.execute(
                "SELECT id, nick, text, created_at FROM comments "
                "WHERE post_id = %s ORDER BY id",
                (post_id,)
            ).fetchall()
        return jsonify(comments=[
            {"id": row[0], "nick": row[1], "text": row[2], "created_at": row[3]}
            for row in rows
        ])

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Expected a JSON object"), 400

    nick = payload.get("nick")
    text = payload.get("text")
    if not isinstance(nick, str) or not isinstance(text, str):
        return jsonify(error="Nick and text are required"), 400

    nick = nick.strip()
    text = text.strip()
    if not nick or len(nick) > MAX_NICK_LENGTH:
        return jsonify(error=f"Nick must contain 1 to {MAX_NICK_LENGTH} characters"), 400
    if not text or len(text) > MAX_COMMENT_LENGTH:
        return jsonify(error=f"Comment must contain 1 to {MAX_COMMENT_LENGTH} characters"), 400

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection(COMMENTS_SCHEMA) as connection:
        cursor = connection.execute(
            "INSERT INTO comments (post_id, nick, text, created_at) "
            "VALUES (%s, %s, %s, %s) RETURNING id, nick, text, created_at",
            (post_id, nick, text, created_at)
        )
        row = cursor.fetchone()
    comment = {"id": row[0], "nick": row[1], "text": row[2], "created_at": row[3]}
    return jsonify(comment=comment), 201


if __name__ == "__main__":
    app.run(host=SERVICE_HOST, port=int(os.environ.get("COMMENTS_SERVICE_PORT", "45001")))
