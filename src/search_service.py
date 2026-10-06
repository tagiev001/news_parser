import os

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)
NEWS_INDEX_URL = os.environ.get(
    "NEWS_INDEX_URL",
    "http://127.0.0.1:45000/api/search-index"
)
REQUEST_TIMEOUT = 5
MAX_QUERY_LENGTH = 100
MAX_RESULTS = 50
SERVICE_HOST = os.environ.get("SEARCH_SERVICE_HOST", "0.0.0.0")


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify(query=query, results=[])
    if len(query) > MAX_QUERY_LENGTH:
        return jsonify(error=f"Search query cannot exceed {MAX_QUERY_LENGTH} characters"), 400

    try:
        response = requests.get(NEWS_INDEX_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        articles = response.json()
    except (requests.RequestException, ValueError):
        app.logger.exception("Could not retrieve the news search index")
        return jsonify(error="News search is temporarily unavailable"), 502
    if not isinstance(articles, list):
        app.logger.error("News search index response must be a JSON array")
        return jsonify(error="News search received an invalid index"), 502

    normalized_query = query.casefold()
    results = []
    for article in articles:
        if not isinstance(article, dict):
            app.logger.error("News search index contains an invalid article")
            return jsonify(error="News search received an invalid index"), 502
        searchable = " ".join(
            str(article.get(field, ""))
            for field in ("title", "text", "name", "date")
        ).casefold()
        if normalized_query not in searchable:
            continue
        results.append(article)
        if len(results) == MAX_RESULTS:
            break

    return jsonify(query=query, results=results)


if __name__ == "__main__":
    app.run(host=SERVICE_HOST, port=int(os.environ.get("SEARCH_SERVICE_PORT", "45002")))
