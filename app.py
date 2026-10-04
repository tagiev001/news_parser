
from io import BytesIO
from pathlib import Path
import sqlite3
from flask import Flask, abort, render_template, send_file


app = Flask(__name__)
DATABASE_PATH = Path(__file__).resolve().with_name("parced_news.db")


def get_articles_from_db():
    with sqlite3.connect(DATABASE_PATH) as connection:
        data = connection.execute(
            "SELECT id, news_title, news_text, university_name, news_date "
            "FROM Posts WHERE deleted = 0 ORDER BY id DESC"
        ).fetchall()
    return [
        {"id": ids, "title": title, "text": text, "name": name, "date": date}
        for ids, title, text, name, date in data
    ]


@app.route("/")
@app.route("/homepage")
def homepage():
    articles = get_articles_from_db()
    return render_template("homepage.html", articles=articles)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/article-image/<int:article_id>")
def article_image(article_id):
    with sqlite3.connect(DATABASE_PATH) as connection:
        row = connection.execute(
            "SELECT news_img FROM Posts WHERE id = ? AND deleted = 0",
            (article_id,)
        ).fetchone()
    if row is None or row[0] is None:
        abort(404)
    return send_file(BytesIO(row[0]), mimetype="image/jpeg")





if __name__ == "__main__":
    app.run(port=45000, debug=True)

















