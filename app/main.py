import os
import json
import io
import uuid
import shutil
import math
import statistics
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, joinedload

from .database import engine, get_db, Base
from .models import DateEntry, DateImage, DateLocation, CommEntry, AppSettings, AuditLog

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Date-abase 💕")

SECRET_KEY      = os.getenv("SECRET_KEY",      "super-secret-love-key-change-me")
SHARED_PASSWORD = os.getenv("SHARED_PASSWORD", "lovebirds")
UPLOAD_DIR      = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
MAX_IMAGE_BYTES    = 15 * 1024 * 1024  # 15 MB

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400)
app.mount("/static",  StaticFiles(directory="app/static"),   name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["hex_idx"] = lambda n: f"0x{n:X}"   # 1→0x1  15→0xF  16→0x10

# ── Comm type definitions ─────────────────────────────────────────────────────
COMM_TYPES = [
    ("💝", "First Ask Out"),
    ("📱", "Text Message"),
    ("📞", "Phone Call"),
    ("💌", "DM / Social Media"),
    ("🤝", "In-Person Chat"),
    ("📧", "Email"),
    ("🎯", "Made It Official"),
    ("🌟", "Special Moment"),
    ("🎉", "Milestone"),
    ("💔", "The Talk"),
    ("📝", "Other"),
]
COMM_TYPE_LABELS = {label: emoji for emoji, label in COMM_TYPES}

# ── Height oracle ideas ───────────────────────────────────────────────────────
HEIGHT_IDEAS = [
    ("The Optimal Romance Angle™", "Lean in at exactly θ = tan⁻¹(14/hinge_magic) ≈ 23°. Science has spoken. The door hinge approves."),
    ("The Forehead Kiss Protocol", "He bends 23 degrees. She gets a forehead kiss. Universe achieves perfect equilibrium. Repeat daily."),
    ("Step Stool Investment Strategy", "A $12 step stool unlocks full eye contact mode. ROI: infinite. Also useful for top-shelf snacks."),
    ("The Human Chin Rest", "Her head is exactly at his heart level. He can rest his chin on her head during long hugs. Ergonomically certified adorable."),
    ("Piggyback Ride Logistics", "Height difference = optimal piggyback geometry. She's already at launching altitude. Zero setup required."),
    ("Concert Survival Mode", "He spots her from literally anywhere. She has an unobstructed view of... his shoulder. Worth it."),
    ("The Armpit Portal", "She fits perfectly under his arm during walks. Scientists call it 'the cozy zone.' It's real. Trust the science."),
    ("Slow Dance Configuration", "Her head lands directly on his chest. She can hear his heartbeat. He thinks his chin rest is cute. Both win."),
    ("The Heel Liberation Act", "She can wear ANY heel height guilt-free. 3 inches? Still shorter. 5 inches? Still adorable. Wear the heels."),
    ("Umbrella Coverage Protocol", "He holds the umbrella. His arm is basically her personal weather system. She stays dry. He gets slightly wet. Love."),
    ("Kitchen Cabinet Division of Labor", "Top shelves: his domain. Bottom cabinets: her expertise. Together they cover 100% of storage. Symbiosis achieved."),
    ("The Spoon Theorem", "14-inch difference produces perfect big-spoon/little-spoon geometry. Mathematically proven. No adjustments needed."),
    ("Dramatic Dip Calculator", "Taller lead = more dramatic dance dip angle. 14 inches = maximum cinematic romance. Take a bow."),
    ("The Surprise Hug Theorem", "She can sneak up and hug him from behind without him seeing it coming. Element of surprise: maximized. Joy: immeasurable."),
    ("Tiara Clearance Certification", "She can wear a full tiara AND still be shorter. Royalty mode: unlocked. Ceiling clearance: confirmed."),
    ("The Jar-Opening Alliance", "He handles jars, high shelves, and lightbulbs. She handles low cabinets and fitting into cozy spaces. Perfectly balanced."),
    ("Movie Night Optimization", "She fits perfectly against his side on the couch. He serves as a personal heated backrest. No blanket needed."),
    ("The 'Lost in a Crowd' Protocol", "She grabs his hand. He's a human lighthouse. Together they navigate any crowd. Navigation success rate: 100%."),
    ("Head-on-Chest Heartbeat Access", "Bonus feature of the 14-inch difference: she gets a live heartbeat monitor during all hugs. Very reassuring. 10/10."),
    ("The Universe Planned This", "Her head: his heart level. His arms: her perfect shelter. The math checks out. 14 inches = 100% chemistry."),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def require_auth(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


# ── Settings & audit helpers ──────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "partner1_name": "Partner 1",
    "partner2_name": "Partner 2",
}

def get_settings(db: Session) -> dict:
    rows = db.query(AppSettings).all()
    s = dict(DEFAULT_SETTINGS)
    for row in rows:
        s[row.key] = row.value
    return s


AUDIT_FIELD_LABELS = {
    "title":               "Title",
    "pre_date_activities": "Pre-date activities",
    "date_datetime":       "Date & time",
    "duration_minutes":    "Duration",
    "location_name":       "Location",
    "what_we_did":         "What we did",
    "notes":               "Notes",
    "rating":              "Rating",
    "comm_datetime":       "Date & time",
    "comm_type":           "Type",
    "description":         "Description",
}

def compute_diff(old_vals: dict, new_vals: dict) -> dict:
    """Return {field: {from, to}} for every field that changed."""
    changes = {}
    for key, new_val in new_vals.items():
        old_val = old_vals.get(key)
        if str(old_val or "") != str(new_val or ""):
            changes[key] = {
                "label": AUDIT_FIELD_LABELS.get(key, key.replace("_", " ").title()),
                "from":  str(old_val) if old_val is not None else None,
                "to":    str(new_val) if new_val is not None else None,
            }
    return changes


def add_audit(
    db: Session,
    *,
    changed_by: str,
    action: str,
    entity_type: str,
    entity_id: int,
    entity_title: str,
    changes: dict | None = None,
) -> None:
    db.add(AuditLog(
        changed_by=changed_by,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_title=entity_title,
        changes_json=json.dumps(changes) if changes else None,
    ))


def save_locations(db: Session, date_id: int, locations_json: str) -> None:
    """Replace all DateLocation rows for a date from a JSON string."""
    db.query(DateLocation).filter(DateLocation.date_id == date_id).delete()
    try:
        locs = json.loads(locations_json) if locations_json.strip() else []
    except Exception:
        locs = []
    for i, loc in enumerate(locs):
        name = (loc.get("name") or "").strip()
        if not name:
            continue
        db.add(DateLocation(
            date_id=date_id,
            name=name,
            lat=loc.get("lat"),
            lon=loc.get("lon"),
            label=(loc.get("label") or "").strip() or None,
            sort_order=i,
        ))


async def save_upload(file: UploadFile) -> str | None:
    """Save an uploaded image; returns stored filename or None if invalid."""
    if not file or not file.filename:
        return None
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        return None
    fname = f"{uuid.uuid4()}{ext}"
    (UPLOAD_DIR / fname).write_bytes(data)
    return fname


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def splash(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("splash.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == SHARED_PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("splash.html", {
        "request": request,
        "error": "Wrong password, babe. Try again. 💔",
    })


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ── Romance Meter ─────────────────────────────────────────────────────────────

ROMANCE_LEVELS = [
    (95, "💥 OVERCLOCK DETECTED",             "overclock"),
    (82, "🔥 Running at Full Capacity",        "hot"),
    (68, "♨️ Optimal Operating Temperature",   "warm"),
    (54, "😊 Warming Up Nicely",               "good"),
    (40, "🌡️ Nominal — Within Parameters",     "neutral"),
    (26, "🥶 Below Expected Threshold",         "cool"),
    (12, "❄️ Critically Underperforming",       "cold"),
    ( 0, "💀 Romance.exe Has Stopped Responding","dead"),
]


def compute_romance_meter(dates, comms) -> dict:
    """
    Proprietary Romance Coefficient™ v2.4.1
    Patent pending. Not FDA approved. Consult a doctor if score exceeds 95.
    """
    if not dates:
        return {"score": 0, "label": "💀 No data — log a date first", "level": "dead",
                "factors": {}, "corrections": []}

    now = datetime.now()

    # ── Factor 1: Date Quality — 35 pts ──────────────────────────────────────
    rated = [d.rating for d in dates if d.rating]
    f_quality = (statistics.mean(rated) / 5 * 35) if rated else 0

    # ── Factor 2: Recency — 25 pts (exponential decay, half-life = 14 days) ──
    days_since = (now - max(d.date_datetime for d in dates)).days
    f_recency = 25 * math.exp(-days_since / 14)

    # ── Factor 3: Commit Frequency — 20 pts ──────────────────────────────────
    first_dt    = min(d.date_datetime for d in dates)
    months_span = max(1, (now - first_dt).days / 30.44)
    avg_pm      = len(dates) / months_span
    f_freq      = min(20, avg_pm * 5)           # 4 dates/month = max

    # ── Factor 4: Adventure Index — 10 pts ───────────────────────────────────
    locs       = set(d.location_name for d in dates if d.location_name)
    f_variety  = min(10, len(locs) / max(len(dates), 1) * 20)

    # ── Factor 5: Communications — 10 pts ────────────────────────────────────
    f_comms = min(10, len(comms) * 0.5)

    raw = f_quality + f_recency + f_freq + f_variety + f_comms

    # ── Correction factors (because love is never simple) ─────────────────────
    corrections = []
    if rated and all(r == 5 for r in rated):
        raw += 3
        corrections.append(("✨ Perfection Coefficient", "+3"))
    if len(comms) > len(dates):
        raw += 2
        corrections.append(("💬 Chatterbox Bonus", "+2"))
    if days_since > 30:
        raw -= 5
        corrections.append(("📅 Neglect Tax (>30 days)", "−5"))
    if avg_pm >= 6:
        raw += 2
        corrections.append(("🚀 Overachiever Bonus (6+/mo)", "+2"))

    score = max(0, min(100, round(raw)))

    label, level = ROMANCE_LEVELS[-1][1], ROMANCE_LEVELS[-1][2]
    for threshold, lbl, lvl in ROMANCE_LEVELS:
        if score >= threshold:
            label, level = lbl, lvl
            break

    return {
        "score": score,
        "label": label,
        "level": level,
        "factors": {
            "quality":   {"pts": round(f_quality, 1),  "max": 35, "label": "Date Quality"},
            "recency":   {"pts": round(f_recency, 1),  "max": 25, "label": "Recency"},
            "frequency": {"pts": round(f_freq, 1),     "max": 20, "label": "Commit Frequency"},
            "variety":   {"pts": round(f_variety, 1),  "max": 10, "label": "Adventure Index"},
            "comms":     {"pts": round(f_comms, 1),    "max": 10, "label": "Comms Logged"},
        },
        "corrections": corrections,
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    dates = db.query(DateEntry).order_by(DateEntry.date_datetime.desc()).all()

    total_minutes = sum(d.duration_minutes for d in dates if d.duration_minutes)
    if total_minutes >= 60:
        time_together = f"{total_minutes // 60}h {total_minutes % 60}m"
    elif total_minutes > 0:
        time_together = f"{total_minutes}m"
    else:
        time_together = "—"

    if dates:
        days_since = (datetime.now() - dates[0].date_datetime).days
        days_since_label = (
            "Today 💕" if days_since == 0
            else "Yesterday" if days_since == 1
            else f"{days_since} days ago"
        )
    else:
        days_since_label = "—"

    ratings = [d.rating for d in dates if d.rating]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    comms = db.query(CommEntry).all()
    romance = compute_romance_meter(dates, comms)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "dates": dates,
        "stats": {
            "total_dates":      len(dates),
            "time_together":    time_together,
            "days_since_label": days_since_label,
            "avg_rating":       avg_rating,
        },
        "romance": romance,
    })


# ── Date CRUD ─────────────────────────────────────────────────────────────────

@app.get("/dates/new", response_class=HTMLResponse)
async def new_date_form(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("date_form.html", {
        "request": request, "entry": None, "error": None,
        "settings": get_settings(db),
        "existing_locs_json": "[]",
    })


@app.post("/dates/new")
async def create_date(
    request: Request,
    title:               str          = Form(...),
    pre_date_activities: str          = Form(""),
    date_datetime:       str          = Form(...),
    duration_hours:      str          = Form(""),
    duration_mins:       str          = Form(""),
    location_name:       str          = Form(""),
    location_lat:        str          = Form(""),
    location_lon:        str          = Form(""),
    what_we_did:         str          = Form(""),
    notes:               str          = Form(""),
    rating:              int          = Form(5),
    changed_by:          str          = Form(""),
    locations_json:      str          = Form(""),
    images:              List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    try:
        dt = datetime.fromisoformat(date_datetime)
    except ValueError:
        return templates.TemplateResponse("date_form.html", {
            "request": request, "entry": None,
            "error": "Invalid date format. 📅",
            "settings": get_settings(db),
        })

    h = int(duration_hours) if duration_hours.strip().isdigit() else 0
    m = int(duration_mins)  if duration_mins.strip().isdigit()  else 0
    total_mins = h * 60 + m

    # Derive a summary location_name from first location for legacy/export compat
    first_loc_name = None
    try:
        locs = json.loads(locations_json) if locations_json.strip() else []
        if locs:
            first_loc_name = locs[0].get("name")
    except Exception:
        pass

    entry = DateEntry(
        title=title,
        pre_date_activities=pre_date_activities or None,
        date_datetime=dt,
        duration_minutes=total_mins if total_mins else None,
        location_name=first_loc_name or location_name or None,
        location_lat=None,
        location_lon=None,
        what_we_did=what_we_did or None,
        notes=notes or None,
        rating=rating,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    save_locations(db, entry.id, locations_json)

    for img_file in images:
        fname = await save_upload(img_file)
        if fname:
            db.add(DateImage(date_id=entry.id, filename=fname))

    add_audit(db, changed_by=changed_by or "Unknown", action="created",
              entity_type="date", entity_id=entry.id, entity_title=entry.title)
    db.commit()

    return RedirectResponse(f"/dates/{entry.id}", status_code=302)


@app.get("/dates/{entry_id}", response_class=HTMLResponse)
async def view_date(request: Request, entry_id: int, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = (
        db.query(DateEntry)
        .options(joinedload(DateEntry.images), joinedload(DateEntry.locations))
        .filter(DateEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    audit_logs = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "date", AuditLog.entity_id == entry_id)
        .order_by(AuditLog.timestamp.desc())
        .all()
    )
    return templates.TemplateResponse("date_detail.html", {
        "request": request, "entry": entry, "audit_logs": audit_logs,
    })


@app.get("/dates/{entry_id}/edit", response_class=HTMLResponse)
async def edit_date_form(request: Request, entry_id: int, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = (
        db.query(DateEntry)
        .options(joinedload(DateEntry.images), joinedload(DateEntry.locations))
        .filter(DateEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    # Build existing-locations JSON for the form JS to pre-populate
    existing_locs = [
        {"name": l.name, "lat": l.lat, "lon": l.lon, "label": l.label or ""}
        for l in entry.locations
    ]
    # Backward-compat: migrate old single-location field into the list if no rows yet
    if not existing_locs and entry.location_name:
        existing_locs = [{"name": entry.location_name,
                          "lat": entry.location_lat,
                          "lon": entry.location_lon, "label": ""}]
    return templates.TemplateResponse("date_form.html", {
        "request": request, "entry": entry, "error": None,
        "settings": get_settings(db),
        "existing_locs_json": json.dumps(existing_locs),
    })


@app.post("/dates/{entry_id}/edit")
async def update_date(
    request: Request,
    entry_id:            int,
    title:               str          = Form(...),
    pre_date_activities: str          = Form(""),
    date_datetime:       str          = Form(...),
    duration_hours:      str          = Form(""),
    duration_mins:       str          = Form(""),
    location_name:       str          = Form(""),
    location_lat:        str          = Form(""),
    location_lon:        str          = Form(""),
    what_we_did:         str          = Form(""),
    notes:               str          = Form(""),
    rating:              int          = Form(5),
    changed_by:          str          = Form(""),
    locations_json:      str          = Form(""),
    delete_images:       str          = Form(""),
    images:              List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = (
        db.query(DateEntry)
        .options(joinedload(DateEntry.images), joinedload(DateEntry.locations))
        .filter(DateEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    try:
        dt = datetime.fromisoformat(date_datetime)
    except ValueError:
        return templates.TemplateResponse("date_form.html", {
            "request": request, "entry": entry, "error": "Invalid date format. 📅",
        })

    # Delete marked images
    to_delete = [int(x) for x in delete_images.split(",") if x.strip().isdigit()]
    for img_id in to_delete:
        img = db.query(DateImage).filter(
            DateImage.id == img_id, DateImage.date_id == entry_id
        ).first()
        if img:
            (UPLOAD_DIR / img.filename).unlink(missing_ok=True)
            db.delete(img)

    # Save new uploads
    for img_file in images:
        fname = await save_upload(img_file)
        if fname:
            db.add(DateImage(date_id=entry.id, filename=fname))

    h = int(duration_hours) if duration_hours.strip().isdigit() else 0
    m = int(duration_mins)  if duration_mins.strip().isdigit()  else 0
    total_mins = h * 60 + m

    # Snapshot before
    old_vals = {
        "title":               entry.title,
        "pre_date_activities": entry.pre_date_activities,
        "date_datetime":       str(entry.date_datetime),
        "duration_minutes":    entry.duration_minutes,
        "location_name":       entry.location_name,
        "what_we_did":         entry.what_we_did,
        "notes":               entry.notes,
        "rating":              entry.rating,
    }

    entry.title               = title
    entry.pre_date_activities = pre_date_activities or None
    entry.date_datetime       = dt
    entry.duration_minutes    = total_mins if total_mins else None
    entry.location_name       = location_name or None
    entry.location_lat        = float(location_lat) if location_lat else None
    entry.location_lon        = float(location_lon) if location_lon else None
    entry.what_we_did         = what_we_did or None
    entry.notes               = notes or None
    entry.rating              = rating

    # Update locations (full replace)
    save_locations(db, entry.id, locations_json)
    # Keep legacy location_name in sync with first stop
    try:
        first_loc = json.loads(locations_json)[0] if locations_json.strip() else None
        entry.location_name = first_loc["name"] if first_loc else None
        entry.location_lat  = first_loc.get("lat")
        entry.location_lon  = first_loc.get("lon")
    except Exception:
        pass

    new_vals = {
        "title":               entry.title,
        "pre_date_activities": entry.pre_date_activities,
        "date_datetime":       str(entry.date_datetime),
        "duration_minutes":    entry.duration_minutes,
        "location_name":       entry.location_name,
        "what_we_did":         entry.what_we_did,
        "notes":               entry.notes,
        "rating":              entry.rating,
    }
    diff = compute_diff(old_vals, new_vals)
    add_audit(db, changed_by=changed_by or "Unknown", action="updated",
              entity_type="date", entity_id=entry.id, entity_title=entry.title,
              changes=diff if diff else None)
    db.commit()
    return RedirectResponse(f"/dates/{entry_id}", status_code=302)


@app.post("/dates/{entry_id}/delete")
async def delete_date(
    request: Request, entry_id: int,
    changed_by: str = Form(""),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = (
        db.query(DateEntry)
        .options(joinedload(DateEntry.images))
        .filter(DateEntry.id == entry_id)
        .first()
    )
    if entry:
        add_audit(db, changed_by=changed_by or "Unknown", action="deleted",
                  entity_type="date", entity_id=entry.id, entity_title=entry.title)
        for img in entry.images:
            (UPLOAD_DIR / img.filename).unlink(missing_ok=True)
        db.delete(entry)
        db.commit()
    return RedirectResponse("/dashboard", status_code=302)


# ── Comms ─────────────────────────────────────────────────────────────────────

@app.get("/comms", response_class=HTMLResponse)
async def comms_list(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    comms = db.query(CommEntry).order_by(CommEntry.comm_datetime.desc()).all()
    return templates.TemplateResponse("comms.html", {
        "request": request, "comms": comms, "comm_types": COMM_TYPES,
    })


@app.get("/comms/new", response_class=HTMLResponse)
async def new_comm_form(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("comm_form.html", {
        "request": request, "entry": None, "error": None,
        "comm_types": COMM_TYPES, "settings": get_settings(db),
    })


@app.post("/comms/new")
async def create_comm(
    request: Request,
    comm_datetime: str = Form(...),
    comm_type:     str = Form(...),
    description:   str = Form(...),
    changed_by:    str = Form(""),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    try:
        dt = datetime.fromisoformat(comm_datetime)
    except ValueError:
        return templates.TemplateResponse("comm_form.html", {
            "request": request, "entry": None,
            "error": "Invalid date format. 📅",
            "comm_types": COMM_TYPES, "settings": get_settings(db),
        })
    entry = CommEntry(comm_datetime=dt, comm_type=comm_type, description=description)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    add_audit(db, changed_by=changed_by or "Unknown", action="created",
              entity_type="comm", entity_id=entry.id,
              entity_title=f"{comm_type}: {description[:60]}")
    db.commit()
    return RedirectResponse("/comms", status_code=302)


@app.get("/comms/{entry_id}/edit", response_class=HTMLResponse)
async def edit_comm_form(request: Request, entry_id: int, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(CommEntry).filter(CommEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Comm not found 💔")
    return templates.TemplateResponse("comm_form.html", {
        "request": request, "entry": entry, "error": None,
        "comm_types": COMM_TYPES, "settings": get_settings(db),
    })


@app.post("/comms/{entry_id}/edit")
async def update_comm(
    request: Request,
    entry_id:      int,
    comm_datetime: str = Form(...),
    comm_type:     str = Form(...),
    description:   str = Form(...),
    changed_by:    str = Form(""),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(CommEntry).filter(CommEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Comm not found 💔")
    try:
        dt = datetime.fromisoformat(comm_datetime)
    except ValueError:
        return templates.TemplateResponse("comm_form.html", {
            "request": request, "entry": entry,
            "error": "Invalid date format. 📅",
            "comm_types": COMM_TYPES, "settings": get_settings(db),
        })
    old_vals = {"comm_datetime": str(entry.comm_datetime), "comm_type": entry.comm_type, "description": entry.description}
    entry.comm_datetime = dt
    entry.comm_type     = comm_type
    entry.description   = description
    new_vals = {"comm_datetime": str(entry.comm_datetime), "comm_type": entry.comm_type, "description": entry.description}
    diff = compute_diff(old_vals, new_vals)
    add_audit(db, changed_by=changed_by or "Unknown", action="updated",
              entity_type="comm", entity_id=entry.id,
              entity_title=f"{comm_type}: {description[:60]}",
              changes=diff if diff else None)
    db.commit()
    return RedirectResponse("/comms", status_code=302)


@app.post("/comms/{entry_id}/delete")
async def delete_comm(
    request: Request, entry_id: int,
    changed_by: str = Form(""),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(CommEntry).filter(CommEntry.id == entry_id).first()
    if entry:
        add_audit(db, changed_by=changed_by or "Unknown", action="deleted",
                  entity_type="comm", entity_id=entry.id,
                  entity_title=f"{entry.comm_type}: {entry.description[:60]}")
        db.delete(entry)
        db.commit()
    return RedirectResponse("/comms", status_code=302)


# ── Settings ─────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": get_settings(db),
        "saved": request.query_params.get("saved"),
    })


@app.post("/settings")
async def save_settings(
    request: Request,
    partner1_name: str = Form(""),
    partner2_name: str = Form(""),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    for key, val in [("partner1_name", partner1_name.strip()), ("partner2_name", partner2_name.strip())]:
        row = db.query(AppSettings).filter(AppSettings.key == key).first()
        if row:
            row.value = val or DEFAULT_SETTINGS[key]
        else:
            db.add(AppSettings(key=key, value=val or DEFAULT_SETTINGS[key]))
    db.commit()
    return RedirectResponse("/settings?saved=1", status_code=302)


# ── Audit Log ─────────────────────────────────────────────────────────────────

@app.get("/audit", response_class=HTMLResponse)
async def audit_log(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()
    return templates.TemplateResponse("audit.html", {
        "request": request, "logs": logs,
    })


# ── Date-alytics ──────────────────────────────────────────────────────────────

def _fmt_mins(m: int | None) -> str:
    if not m: return "—"
    h, rem = divmod(int(m), 60)
    if h and rem: return f"{h}h {rem}m"
    return f"{h}h" if h else f"{rem}m"


def compute_analytics(dates, comms, images_count: int, audit_logs) -> dict:
    if not dates:
        return {"empty": True}

    now = datetime.now()
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # ── Temporal basics ───────────────────────────────────────────────────────
    sorted_dates = sorted(dates, key=lambda d: d.date_datetime)
    first        = sorted_dates[0]
    latest       = sorted_dates[-1]
    rel_days     = max(1, (now - first.date_datetime).days)
    months_span  = max(1, rel_days / 30.44)
    weeks_span   = max(1, rel_days / 7)

    # ── Duration ──────────────────────────────────────────────────────────────
    with_dur  = [d for d in dates if d.duration_minutes]
    total_m   = sum(d.duration_minutes for d in with_dur)
    avg_m     = statistics.mean(d.duration_minutes for d in with_dur) if with_dur else None
    longest   = max(with_dur, key=lambda d: d.duration_minutes) if with_dur else None
    shortest  = min(with_dur, key=lambda d: d.duration_minutes) if with_dur else None

    # ── Ratings ───────────────────────────────────────────────────────────────
    rated     = [d.rating for d in dates if d.rating]
    avg_r     = round(statistics.mean(rated), 2) if rated else None
    perfect   = sum(1 for r in rated if r == 5)
    low       = sum(1 for r in rated if r and r <= 2)
    rat_dist  = [(i, rated.count(i)) for i in range(1, 6)]

    # Rating trend: compare avg of first-half vs second-half
    half = len(sorted_dates) // 2
    if half >= 2:
        first_avg = statistics.mean(d.rating for d in sorted_dates[:half] if d.rating) or 0
        last_avg  = statistics.mean(d.rating for d in sorted_dates[half:] if d.rating) or 0
        delta     = round(last_avg - first_avg, 2)
        trend     = ("📈 Improving" if delta > 0.2 else "📉 Declining" if delta < -0.2 else "➡️ Stable")
        trend_delta = delta
    else:
        trend = "➡️ Too early to tell"
        trend_delta = 0

    # ── Day of week ───────────────────────────────────────────────────────────
    dow_counts = Counter(d.date_datetime.weekday() for d in dates)
    dow_max    = max(dow_counts.values(), default=1)
    dow_data   = [(DAY_NAMES[i], dow_counts.get(i, 0),
                   round(dow_counts.get(i, 0) / dow_max * 100)) for i in range(7)]
    fav_day    = DAY_NAMES[dow_counts.most_common(1)[0][0]] if dow_counts else "—"

    # ── Time of day ───────────────────────────────────────────────────────────
    def tod(dt):
        h = dt.hour
        if  5 <= h < 12: return "🌅 Morning"
        if 12 <= h < 17: return "☀️ Afternoon"
        if 17 <= h < 21: return "🌆 Evening"
        return "🌙 Night Owl"
    tod_counts = Counter(tod(d.date_datetime) for d in dates)
    tod_max    = max(tod_counts.values(), default=1)
    tod_order  = ["🌅 Morning","☀️ Afternoon","🌆 Evening","🌙 Night Owl"]
    tod_data   = [(t, tod_counts.get(t, 0),
                   round(tod_counts.get(t, 0) / tod_max * 100)) for t in tod_order]
    fav_tod    = tod_counts.most_common(1)[0][0] if tod_counts else "—"

    # ── Monthly chart (last 12 months) ────────────────────────────────────────
    months = []
    for i in range(11, -1, -1):
        m_dt   = now.replace(day=1) - timedelta(days=i * 30)
        m_key  = m_dt.strftime("%Y-%m")
        m_lbl  = m_dt.strftime("%b '%y")
        months.append((m_key, m_lbl))
    m_counts  = Counter(d.date_datetime.strftime("%Y-%m") for d in dates)
    m_max     = max((m_counts.get(k, 0) for k, _ in months), default=1)
    month_data = [(lbl, m_counts.get(k, 0),
                   round(m_counts.get(k, 0) / max(m_max, 1) * 100)) for k, lbl in months]
    busiest_m_key = m_counts.most_common(1)[0][0] if m_counts else None

    # ── Locations ─────────────────────────────────────────────────────────────
    locs        = [d.location_name for d in dates if d.location_name]
    uniq_locs   = len(set(locs))
    fav_loc     = Counter(locs).most_common(1)[0] if locs else None   # (name, count)
    pct_located = round(len(locs) / len(dates) * 100) if dates else 0

    # ── Comms ─────────────────────────────────────────────────────────────────
    top_comm_type = Counter(c.comm_type for c in comms).most_common(1)[0] if comms else None

    # ── Audit ──────────────────────────────────────────────────────────────────
    editor_counts = Counter(log.changed_by for log in audit_logs if log.action != "deleted")
    top_editor    = editor_counts.most_common(1)[0] if editor_counts else None

    # ── Love uptime (% of weeks with ≥1 date) ─────────────────────────────────
    weeks_with = len({d.date_datetime.isocalendar()[:2] for d in dates})
    uptime_pct = min(100, round(weeks_with / weeks_span * 100, 1))

    # ── Relationship version (semantic-ish) ───────────────────────────────────
    major = int(months_span)
    minor = len(dates)
    patch = perfect
    rel_version = f"v{major}.{minor}.{patch}"

    # ── Funny build status ────────────────────────────────────────────────────
    if avg_r is None:      build = ("⚪ UNRATED", "gray")
    elif avg_r >= 4.5:     build = ("✅ PASSING", "green")
    elif avg_r >= 3.5:     build = ("⚠️ UNSTABLE", "yellow")
    else:                  build = ("❌ FAILING",  "red")

    maintenance = (
        "🚨 Date night critically overdue!" if (now - latest.date_datetime).days > 30
        else "⚠️  Schedule a date soon"     if (now - latest.date_datetime).days > 14
        else "✅ All systems nominal"
    )

    return {
        "empty":          False,
        "total_dates":    len(dates),
        "total_comms":    len(comms),
        "total_photos":   images_count,
        "rel_days":       rel_days,
        "rel_version":    rel_version,
        "first_date":     first,
        "latest_date":    latest,
        "days_since":     (now - latest.date_datetime).days,
        "avg_per_month":  round(len(dates) / months_span, 1),
        "avg_per_week":   round(len(dates) / weeks_span, 2),
        "total_mins":     total_m,
        "total_fmt":      _fmt_mins(total_m),
        "avg_mins":       avg_m,
        "avg_fmt":        _fmt_mins(int(avg_m)) if avg_m else "—",
        "longest":        longest,
        "longest_fmt":    _fmt_mins(longest.duration_minutes) if longest else "—",
        "shortest":       shortest,
        "shortest_fmt":   _fmt_mins(shortest.duration_minutes) if shortest else "—",
        "avg_rating":     avg_r,
        "perfect":        perfect,
        "perfect_pct":    round(perfect / len(dates) * 100) if dates else 0,
        "low_rated":      low,
        "rat_dist":       rat_dist,
        "rat_max":        max(c for _, c in rat_dist) or 1,
        "trend":          trend,
        "trend_delta":    trend_delta,
        "dow_data":       dow_data,
        "fav_day":        fav_day,
        "tod_data":       tod_data,
        "fav_tod":        fav_tod,
        "month_data":     month_data,
        "uniq_locs":      uniq_locs,
        "fav_loc":        fav_loc,
        "pct_located":    pct_located,
        "top_comm_type":  top_comm_type,
        "top_editor":     top_editor,
        "uptime_pct":     uptime_pct,
        "build":          build,
        "maintenance":    maintenance,
        "total_heart_h":  round(sum((d.rating or 0) * (d.duration_minutes or 0) for d in dates) / 60, 1),
    }


@app.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    from .models import DateImage
    dates       = db.query(DateEntry).order_by(DateEntry.date_datetime).all()
    comms       = db.query(CommEntry).all()
    img_count   = db.query(DateImage).count()
    audit_logs  = db.query(AuditLog).all()
    stats       = compute_analytics(dates, comms, img_count, audit_logs)
    return templates.TemplateResponse("analytics.html", {
        "request": request, "stats": stats,
    })


# ── Height Oracle ─────────────────────────────────────────────────────────────

@app.get("/magic-ball", response_class=HTMLResponse)
async def magic_ball(request: Request):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("magic_ball.html", {"request": request})


@app.get("/api/magic-ball-idea")
async def get_idea(request: Request):
    if not require_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    import random
    title, idea = random.choice(HEIGHT_IDEAS)
    return JSONResponse({"title": title, "idea": idea})


# ── Import / Export ───────────────────────────────────────────────────────────

@app.get("/export")
async def export_data(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    dates = db.query(DateEntry).order_by(DateEntry.date_datetime).all()
    comms = db.query(CommEntry).order_by(CommEntry.comm_datetime).all()
    data = {
        "export_date": datetime.now().isoformat(),
        "app": "Date-abase 💕",
        "dates": [d.to_dict() for d in dates],
        "comms": [c.to_dict() for c in comms],
    }
    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dateabase-export.json"},
    )


@app.post("/import")
async def import_data(
    request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    try:
        data = json.loads(await file.read())
        imported_dates = imported_comms = 0

        for item in data.get("dates", []):
            # ── Robust datetime parse ─────────────────────────────────────────
            raw_dt = item.get("date_datetime") or item.get("date") or item.get("datetime")
            try:
                dt = datetime.fromisoformat(str(raw_dt)) if raw_dt else datetime.now()
            except (ValueError, TypeError):
                dt = datetime.now()

            # ── Duration: accept minutes int OR legacy h/m dict ───────────────
            dur = item.get("duration_minutes")
            if dur is None:
                h = int(item.get("duration_hours", 0) or 0)
                m = int(item.get("duration_mins",  0) or 0)
                dur = h * 60 + m or None
            else:
                try:
                    dur = int(dur)
                except (ValueError, TypeError):
                    dur = None

            # ── First location name for legacy field ──────────────────────────
            locs_raw   = item.get("locations") or []
            first_name = item.get("location_name")
            first_lat  = item.get("location_lat")
            first_lon  = item.get("location_lon")
            if locs_raw:
                first_name = locs_raw[0].get("name", first_name)
                first_lat  = locs_raw[0].get("lat",  first_lat)
                first_lon  = locs_raw[0].get("lon",  first_lon)

            entry = DateEntry(
                title               = item.get("title") or "Untitled Date",
                pre_date_activities = item.get("pre_date_activities"),
                date_datetime       = dt,
                duration_minutes    = dur,
                location_name       = first_name,
                location_lat        = float(first_lat) if first_lat else None,
                location_lon        = float(first_lon) if first_lon else None,
                what_we_did         = item.get("what_we_did"),
                notes               = item.get("notes"),
                rating              = int(item.get("rating") or 5),
            )
            db.add(entry)
            db.flush()   # get entry.id before creating child records

            # ── Create DateLocation rows ──────────────────────────────────────
            if locs_raw:
                for i, loc in enumerate(locs_raw):
                    name = (loc.get("name") or "").strip()
                    if not name:
                        continue
                    db.add(DateLocation(
                        date_id    = entry.id,
                        name       = name,
                        lat        = loc.get("lat"),
                        lon        = loc.get("lon"),
                        label      = loc.get("label") or None,
                        sort_order = i,
                    ))
            elif first_name:
                # Migrate legacy single-location field into DateLocation
                db.add(DateLocation(
                    date_id    = entry.id,
                    name       = first_name,
                    lat        = float(first_lat) if first_lat else None,
                    lon        = float(first_lon) if first_lon else None,
                    sort_order = 0,
                ))

            imported_dates += 1

        for item in data.get("comms", []):
            raw_dt = item.get("comm_datetime") or item.get("datetime")
            try:
                dt = datetime.fromisoformat(str(raw_dt)) if raw_dt else datetime.now()
            except (ValueError, TypeError):
                dt = datetime.now()
            db.add(CommEntry(
                comm_datetime = dt,
                comm_type     = item.get("comm_type") or "Other",
                description   = item.get("description") or "",
            ))
            imported_comms += 1

        db.commit()
        return RedirectResponse(
            f"/dashboard?imported={imported_dates}&imported_comms={imported_comms}",
            status_code=302,
        )
    except Exception as exc:
        db.rollback()
        return RedirectResponse("/dashboard?import_error=1", status_code=302)
