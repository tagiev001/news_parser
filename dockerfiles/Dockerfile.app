FROM python:3.14-slim

WORKDIR /app

ENV STATISTICS_SERVICE_URL=http://np.stat:45003
ENV SEARCH_SERVICE_URL=http://np.search:45002
ENV COMMENTS_SERVICE_URL=http://np.comments:45001


COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/__init__.py ./src/
COPY src/app.py ./src/
COPY src/database.py ./src/

COPY static/ ./static/
COPY templates/ ./templates/

CMD ["python", "-m", "src.app"]
