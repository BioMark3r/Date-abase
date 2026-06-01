FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data /data/uploads

ENV DATABASE_URL=sqlite:////data/dateabase.db
ENV UPLOAD_DIR=/data/uploads
ENV SECRET_KEY=change-me-to-something-secret
ENV SHARED_PASSWORD=lovebirds

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
