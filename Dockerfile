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
ENV SECRET_KEY=change-me-to-something-very-secret

# Default credentials — works out of the box, change via Settings > Change Password after first login
ENV PARTNER1_NAME="Partner 1"
ENV PARTNER1_PASSWORD=lovebirds1
ENV PARTNER2_NAME="Partner 2"
ENV PARTNER2_PASSWORD=lovebirds2

# WebAuthn / Face ID — set to your Cloudflare Tunnel domain in production
# e.g. APP_DOMAIN=dates.yourdomain.com  APP_ORIGIN=https://dates.yourdomain.com
ENV APP_DOMAIN=localhost
ENV APP_ORIGIN=http://localhost:8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
