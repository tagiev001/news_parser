FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STATISTICS_SERVICE_URL=http://stat:45003 \
    SEARCH_SERVICE_URL=http://search:45002 \
    COMMENTS_SERVICE_URL=http://comments:45001 \
    SITE_HOST=0.0.0.0 \
    SITE_PORT=45000



COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY src/__init__.py ./src/
COPY src/app.py ./src/
COPY src/database.py ./src/

COPY static/ ./static/
COPY templates/ ./templates/

EXPOSE 45000/tcp

USER app

CMD ["python", "-m", "src.app"]
