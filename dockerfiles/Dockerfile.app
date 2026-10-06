FROM python:3.14-slim

WORKDIR /app

ENV COMMENTS_SERVICE_URL=http://comments-service:45001
ENV SEARCH_SERVICE_URL=http://search-service:8000

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/__init__.py ./src/
COPY src/app.py ./src/
COPY src/database.py ./src/

COPY static/ ./static/
COPY templates/ ./templates/

CMD ["python", "-m", "src.app"]
