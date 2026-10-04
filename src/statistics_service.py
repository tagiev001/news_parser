import os
import uuid

from flask import Flask, abort, jsonify, request

from .database import get_connection


app = Flask(__name__)
SERVICE_HOST = os.environ.get("STATISTICS_SERVICE_HOST", "0.0.0.0")
SERVICE_PORT = int(os.environ.get("STATISTICS_SERVICE_PORT", "45003"))
MAX_BATCH_SIZE = 100


def parse_voter_id(payload):
    voter_id = payload.get("voter_id") if isinstance(payload, dict) else None
    try:
        return str(uuid.UUID(voter_id))
    except (ValueError, TypeError, AttributeError):
        abort(400, description="A valid voter_id is required")


@app.route("/posts/<int:post_id>/views", methods=["POST"])
def record_view(post_id):
    if post_id < 1:
        abort(400, description="Post ID must be positive")
    voter_id = parse_voter_id(request.get_json(silent=True))

    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO post_views (post_id, voter_id) VALUES (%s, %s) "
            "ON CONFLICT (post_id, voter_id) DO NOTHING RETURNING post_id",
            (post_id, voter_id)
        )
        views = connection.execute(
            "SELECT COUNT(*) FROM post_views WHERE post_id = %s",
            (post_id,)
        ).fetchone()[0]
    return jsonify(views=views, viewed=cursor.fetchone() is not None)


@app.route("/posts/<int:post_id>/likes", methods=["POST"])
def toggle_like(post_id):
    if post_id < 1:
        abort(400, description="Post ID must be positive")
    voter_id = parse_voter_id(request.get_json(silent=True))

    with get_connection() as connection:
        inserted = connection.execute(
            "INSERT INTO post_likes (post_id, voter_id) VALUES (%s, %s) "
            "ON CONFLICT (post_id, voter_id) DO NOTHING RETURNING post_id",
            (post_id, voter_id)
        ).fetchone()
        if inserted is None:
            connection.execute(
                "DELETE FROM post_likes WHERE post_id = %s AND voter_id = %s",
                (post_id, voter_id)
            )
            liked = False
        else:
            liked = True
        likes = connection.execute(
            "SELECT COUNT(*) FROM post_likes WHERE post_id = %s",
            (post_id,)
        ).fetchone()[0]
    return jsonify(liked=liked, likes=likes)


@app.route("/stats")
def get_stats():
    raw_ids = request.args.getlist("post_id")
    if not raw_ids:
        return jsonify(stats=[])
    if len(raw_ids) > MAX_BATCH_SIZE:
        abort(400, description=f"At most {MAX_BATCH_SIZE} post IDs are allowed")
    try:
        post_ids = list(dict.fromkeys(int(value) for value in raw_ids))
    except ValueError:
        abort(400, description="post_id values must be integers")
    if any(post_id < 1 for post_id in post_ids):
        abort(400, description="Post IDs must be positive")

    placeholders = ",".join("%s" for _ in post_ids)
    with get_connection() as connection:
        view_counts = dict(connection.execute(
            f"SELECT post_id, COUNT(*) FROM post_views WHERE post_id IN ({placeholders}) GROUP BY post_id",
            post_ids
        ).fetchall())
        like_counts = dict(connection.execute(
            f"SELECT post_id, COUNT(*) FROM post_likes WHERE post_id IN ({placeholders}) GROUP BY post_id",
            post_ids
        ).fetchall())
    stats = [
        {"post_id": post_id, "views": view_counts.get(post_id, 0), "likes": like_counts.get(post_id, 0)}
        for post_id in post_ids
    ]
    return jsonify(stats=stats)


if __name__ == "__main__":
    app.run(host=SERVICE_HOST, port=SERVICE_PORT)
