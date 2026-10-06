# University news site

Python applications and services are in `src/`; Flask templates and static
assets remain in the project-root `templates/` and `static/` directories. The
site, crawler, comments, and statistics service share PostgreSQL, configured
with `DATABASE_URL`.

Install dependencies and set a PostgreSQL connection URL before starting:

```sh
python -m pip install -r requirements.txt
createdb news_parser
export DATABASE_URL='postgresql://user:password@localhost:5432/news_parser'
```

The applications create their tables with `CREATE TABLE IF NOT EXISTS` when
the first database connection is made. News posts live in the `news` schema
(shared by the site and crawler), comments live in `comments`, and views and
likes live in `statistics`. The database user must be allowed to create
schemas. Search reads the site API and does not connect to PostgreSQL. Existing
tables in `public` are not moved automatically; migrate them before deployment
if their data must be preserved. Existing SQLite databases are not imported or
migrated.

Start each process from the project root in a separate terminal:

```sh
python -m src.app
python -m src.comments_service
python -m src.search_service
python -m src.statistics_service
```

Alternatively, run `bash startup` to start all four services together.

The web processes listen on `0.0.0.0` by default. Override their bind addresses
with `SITE_HOST`, `COMMENTS_SERVICE_HOST`, `SEARCH_SERVICE_HOST`, and
`STATISTICS_SERVICE_HOST` if needed.
The comments, search, and statistics services expose `GET /health` endpoints
that return HTTP 200 while their process is responding. The statistics page
checks these endpoints and displays each service's availability.

Run the news scraper separately when required:

```sh
python -m src.crawler_service
```

Run the test suite with the standard-library unittest runner:

```sh
python -m unittest discover -s tests -v
```
