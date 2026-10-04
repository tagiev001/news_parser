
from io import BytesIO
import os
from pathlib import Path
import requests
from flask import Flask, abort, jsonify, render_template, request, send_file

from .database import get_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
app = Flask(
    __name__,
    template_folder=PROJECT_ROOT / "templates",
    static_folder=PROJECT_ROOT / "static",
)
PAGE_SIZE = 9
COMMENTS_SERVICE_URL = os.environ.get("COMMENTS_SERVICE_URL", "http://127.0.0.1:45001")
SEARCH_SERVICE_URL = os.environ.get("SEARCH_SERVICE_URL", "http://127.0.0.1:45002")
STATISTICS_SERVICE_URL = os.environ.get("STATISTICS_SERVICE_URL", "http://127.0.0.1:45003")
SERVICE_TIMEOUT = 7
SITE_HOST = os.environ.get("SITE_HOST", "0.0.0.0")
SITE_PORT = int(os.environ.get("SITE_PORT", "45000"))


def get_post_stats(post_ids):
    if not post_ids:
        return {}, True
    stats_by_id = {}
    for start in range(0, len(post_ids), 100):
        try:
            response = requests.get(
                f"{STATISTICS_SERVICE_URL}/stats",
                params=[("post_id", post_id) for post_id in post_ids[start:start + 100]],
                timeout=2
            )
            response.raise_for_status()
            stats = response.json()["stats"]
            if not isinstance(stats, list):
                raise ValueError("Statistics response must contain a list")
            stats_by_id.update({
                int(row["post_id"]): {
                    "views": int(row["views"]),
                    "likes": int(row["likes"]),
                }
                for row in stats
            })
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            app.logger.warning("Post statistics unavailable; serving news without counters: %s", error)
            return {}, False
    return stats_by_id, True


def get_articles_from_db(limit=PAGE_SIZE, offset=0):
    with get_connection() as connection:
        data = connection.execute(
            "SELECT id, news_title, news_text, university_name, news_date "
            "FROM posts WHERE deleted = 0 ORDER BY id DESC LIMIT %s OFFSET %s",
            (limit + 1, offset)
        ).fetchall()
    stats, statistics_available = get_post_stats([row[0] for row in data[:limit]])
    articles = [
        {
            "id": article_id,
            "title": title,
            "text": text,
            "name": name,
            "date": date,
            "image_url": f"/article-image/{article_id}",
            "views": stats.get(article_id, {}).get("views"),
            "likes": stats.get(article_id, {}).get("likes"),
        }
        for article_id, title, text, name, date in data[:limit]
    ]
    return articles, len(data) > limit, statistics_available


@app.route("/")
@app.route("/homepage")
def homepage():
    articles, has_more, statistics_available = get_articles_from_db()
    return render_template(
        "homepage.html",
        articles=articles,
        has_more=has_more,
        statistics_available=statistics_available,
        page_size=PAGE_SIZE,
    )


@app.route("/load_articles")
def load_articles():
    try:
        offset = int(request.args.get("offset", "0"))
        limit = int(request.args.get("limit", str(PAGE_SIZE)))
    except ValueError:
        abort(400, description="offset and limit must be integers")

    if offset < 0 or limit < 1:
        abort(400, description="offset must be non-negative and limit must be positive")

    articles, has_more, statistics_available = get_articles_from_db(
        limit=min(limit, PAGE_SIZE),
        offset=offset
    )
    return jsonify(
        articles=articles,
        has_more=has_more,
        statistics_available=statistics_available
    )


@app.route("/statistics")
def statistics():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, news_title, university_name, news_date "
            "FROM posts WHERE deleted = 0 ORDER BY id DESC"
        ).fetchall()

    stats, statistics_available = get_post_stats([row[0] for row in rows])
    articles = [
        {
            "id": article_id,
            "title": title,
            "name": name,
            "date": date,
            "views": stats.get(article_id, {}).get("views"),
            "likes": stats.get(article_id, {}).get("likes"),
        }
        for article_id, title, name, date in rows
    ]
    if statistics_available:
        articles.sort(key=lambda article: (article["views"], article["likes"]), reverse=True)
        total_views = sum(article["views"] for article in articles)
        total_likes = sum(article["likes"] for article in articles)
    else:
        total_views = total_likes = None

    return render_template(
        "statistics.html",
        articles=articles,
        article_count=len(articles),
        total_views=total_views,
        total_likes=total_likes,
        statistics_available=statistics_available,
    )


@app.route("/api/search-index")
def search_index():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, news_title, news_text, university_name, news_date "
            "FROM posts WHERE deleted = 0 ORDER BY id DESC"
        ).fetchall()
    return jsonify([
        {
            "id": article_id,
            "title": title,
            "text": text,
            "name": name,
            "date": date,
            "image_url": f"/article-image/{article_id}",
        }
        for article_id, title, text, name, date in rows
    ])


def proxy_service_json(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=SERVICE_TIMEOUT, **kwargs)
    except requests.RequestException:
        app.logger.exception("Downstream service request failed: %s %s", method, url)
        return jsonify(error="The requested service is temporarily unavailable"), 503

    try:
        payload = response.json()
    except ValueError:
        app.logger.error("Downstream service returned non-JSON response: %s %s", method, url)
        return jsonify(error="The requested service returned an invalid response"), 502
    return jsonify(payload), response.status_code


@app.route("/search-api")
def search_api():
    return proxy_service_json(
        "GET",
        f"{SEARCH_SERVICE_URL}/search",
        params={"q": request.args.get("q", "")}
    )


@app.route("/comments/posts/<int:post_id>", methods=["GET", "POST"])
def comments_api(post_id):
    with get_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM posts WHERE id = %s AND deleted = 0",
            (post_id,)
        ).fetchone()
    if exists is None:
        abort(404, description="Post not found")

    payload = request.get_json(silent=True) if request.method == "POST" else None
    return proxy_service_json(
        request.method,
        f"{COMMENTS_SERVICE_URL}/posts/{post_id}/comments",
        json=payload if request.method == "POST" else None
    )


@app.route("/posts/<int:article_id>/view", methods=["POST"])
def record_post_view(article_id):
    return proxy_post_stat_event(article_id, "views")


@app.route("/posts/<int:article_id>/like", methods=["POST"])
def toggle_post_like(article_id):
    return proxy_post_stat_event(article_id, "likes")


def proxy_post_stat_event(article_id, event):
    with get_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM posts WHERE id = %s AND deleted = 0",
            (article_id,)
        ).fetchone()
    if exists is None:
        abort(404, description="Post not found")
    return proxy_service_json(
        "POST",
        f"{STATISTICS_SERVICE_URL}/posts/{article_id}/{event}",
        json=request.get_json(silent=True)
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/article-image/<int:article_id>")
def article_image(article_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT news_img FROM posts WHERE id = %s AND deleted = 0",
            (article_id,)
        ).fetchone()
    if row is None or row[0] is None:
        abort(404)
    return send_file(BytesIO(row[0]), mimetype="image/jpeg")





if __name__ == "__main__":
    app.run(host=SITE_HOST, port=SITE_PORT, debug=True)
