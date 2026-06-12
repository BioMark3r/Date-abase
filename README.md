# 💕 Date-abase

> *A very scientific record of romance, engineered with love.*

A humorous, cute web application for logging and reliving your dates — complete with a **Height Difference Oracle**, interactive map location picker, heart ratings, and full JSON import/export. Because every great love story deserves a database.

```
14 inches of height difference. 100% chemistry.
θ = tan⁻¹( Height Diff / Hinge Magic ) ≈ 23°
```

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔐 **Shared Password Auth** | Simple splash-screen login — one password, two lovebirds |
| 📋 **Date Logging** | Title, pre-date activities, what happened, notes, duration & heart rating (1–5 ❤️) |
| 📍 **Map Location Picker** | Search and pin any location using Leaflet.js + OpenStreetMap (no API key needed) |
| 🔮 **Height Difference Oracle** | Magic 8-ball style idea generator with 20 scientifically-certified tips for managing a 14″ height gap |
| 📤 **JSON Export** | Download your entire date history as a portable `.json` file |
| 📥 **JSON Import** | Restore or migrate data from a previously exported file |
| 💅 **Romantic Theme** | White background, pink/rose colour scheme, floating hearts, Playfair Display typography |
| 🐳 **Single Docker Container** | SQLite embedded — zero external dependencies, one command to deploy |

---

## 🚀 Quick Start

### With Docker Compose (recommended)

```bash
git clone https://github.com/BioMark3r/Date-abase.git
cd Date-abase
docker compose up -d
```

Open **http://localhost:8000** — default password is `lovebirds`.

> 💡 Data is stored in a named Docker volume (`dateabase_data`) so it survives container restarts and updates.

### With Docker directly

```bash
docker build -t dateabase .
docker run -d \
  -p 8000:8000 \
  -v dateabase_data:/data \
  -e SHARED_PASSWORD=yourpassword \
  -e SECRET_KEY=change-me-to-something-secret \
  --name dateabase \
  dateabase
```

### Local development (without Docker)

```bash
# Clone and set up a virtual environment
git clone https://github.com/BioMark3r/Date-abase.git
cd Date-abase
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create local data directory
mkdir -p data

# Run the dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## ⚙️ Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|---|---|---|
| `PARTNER1_NAME` / `PARTNER2_NAME` | `Partner 1` / `Partner 2` | Display names for the two accounts |
| `PARTNER1_PASSWORD` / `PARTNER2_PASSWORD` | `lovebirds1` / `lovebirds2` | First-boot passwords (change in Settings afterward; env is ignored once set) |
| `SECRET_KEY` | `super-secret-love-key-change-me` | Session signing key — **required in production** (the app refuses to boot with the default when `APP_DOMAIN` isn't `localhost`) |
| `APP_DOMAIN` | `localhost` | WebAuthn Relying-Party ID — must equal the hostname in the browser URL (no port) |
| `APP_ORIGIN` | `http://localhost:8000` | WebAuthn origin — must exactly match the browser's `scheme://host` (e.g. `https://yourpi.tailXXXX.ts.net`) |
| `DATABASE_URL` | `sqlite:////data/dateabase.db` | SQLAlchemy DB URL — SQLite path inside Docker volume |

### 🔐 Face ID / Tailscale deployment

Face ID (WebAuthn) only works over HTTPS, and `APP_DOMAIN`/`APP_ORIGIN` must **exactly** match the URL your browser uses. With Tailscale Funnel that's your `*.ts.net` hostname on port 443 (no `:8000`).

`docker-compose.yml` ships with `localhost` defaults. **Don't edit it on your server** — a `git pull` can reset it (and break Face ID with *"The RP ID localhost is invalid for this domain"*). Instead use a gitignored per-host override:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
# edit APP_DOMAIN / APP_ORIGIN (and SECRET_KEY) to match your Tailscale host
docker compose up -d
```

Compose auto-merges `docker-compose.override.yml` over `docker-compose.yml`, and it's gitignored, so your real domain survives every pull. Verify with:

```bash
docker compose exec dateabase printenv APP_DOMAIN APP_ORIGIN
```

---

## 🗂️ Project Structure

```
Date-abase/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
└── app/
    ├── __init__.py
    ├── main.py          # All routes: auth, CRUD, oracle, import/export
    ├── database.py      # SQLAlchemy engine & session setup
    ├── models.py        # DateEntry ORM model
    ├── static/
    │   └── css/
    │       └── style.css
    └── templates/
        ├── base.html        # Shared navbar/footer layout
        ├── splash.html      # Login page with SVG hero graphic
        ├── dashboard.html   # Date list with stats
        ├── date_form.html   # Create / edit form + map picker
        ├── date_detail.html # Full date view with map
        └── magic_ball.html  # Height Difference Oracle 🔮
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) + [Jinja2](https://jinja.palletsprojects.com/) templates |
| **Database** | [SQLite](https://www.sqlite.org/) via [SQLAlchemy](https://www.sqlalchemy.org/) ORM |
| **Auth** | Starlette `SessionMiddleware` (signed cookie) |
| **Maps** | [Leaflet.js](https://leafletjs.com/) + [OpenStreetMap](https://www.openstreetmap.org/) + Nominatim geocoding |
| **Fonts** | Google Fonts — Playfair Display & Lato |
| **Container** | Docker + Docker Compose |

No JavaScript frameworks, no external databases, no API keys required.

---

## 🔮 The Height Difference Oracle

Inspired by the **Door Hinge Theory of Love** — *"Love is all about finding the right pivot point"* — the oracle dispenses 20 pieces of peer-reviewed* relationship advice for couples with a 14-inch height difference.

Topics covered include: forehead kiss geometry, step-stool investment strategy, optimal slow-dance configuration, concert survival tactics, the human chin-rest theorem, and much more.

> *\*Not actually peer-reviewed. Certified only by the hinge.*

---

## 📦 Updating

```bash
git pull
docker compose up -d --build
```

Your data volume is untouched during updates.

---

## 📤 Data Portability

- **Export:** Click *Export JSON* on the dashboard to download all dates as `dateabase-export.json`
- **Import:** Click *Import JSON* and select a previously exported file — entries are appended (no duplicates check, by design)

Export format:
```json
{
  "export_date": "2025-02-14T20:00:00",
  "app": "Date-abase 💕",
  "dates": [
    {
      "id": 1,
      "title": "Sunset Picnic",
      "date_datetime": "2025-02-14T18:30:00",
      "duration_minutes": 180,
      "location_name": "Central Park, New York",
      "location_lat": 40.785091,
      "location_lon": -73.968285,
      "pre_date_activities": "...",
      "what_we_did": "...",
      "notes": "...",
      "rating": 5
    }
  ]
}
```

---

## 💕 Made With

- Love
- Basic engineering principles  
- A 14-inch height difference
- 100% chemistry

---

*"Engineering the little things that bring us closer."*
