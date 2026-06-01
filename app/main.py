import os
import json
import io
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import List
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, joinedload

from .database import engine, get_db, Base
from .models import DateEntry, DateImage, CommEntry, AppSettings, AuditLog

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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "dates": dates,
        "stats": {
            "total_dates":    len(dates),
            "time_together":  time_together,
            "days_since_label": days_since_label,
            "avg_rating":     avg_rating,
        },
    })


# ── Date CRUD ─────────────────────────────────────────────────────────────────

@app.get("/dates/new", response_class=HTMLResponse)
async def new_date_form(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("date_form.html", {
        "request": request, "entry": None, "error": None,
        "settings": get_settings(db),
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

    entry = DateEntry(
        title=title,
        pre_date_activities=pre_date_activities or None,
        date_datetime=dt,
        duration_minutes=total_mins if total_mins else None,
        location_name=location_name or None,
        location_lat=float(location_lat) if location_lat else None,
        location_lon=float(location_lon) if location_lon else None,
        what_we_did=what_we_did or None,
        notes=notes or None,
        rating=rating,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

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
        .options(joinedload(DateEntry.images))
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
        .options(joinedload(DateEntry.images))
        .filter(DateEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    return templates.TemplateResponse("date_form.html", {
        "request": request, "entry": entry, "error": None,
        "settings": get_settings(db),
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
    delete_images:       str          = Form(""),
    images:              List[UploadFile] = File(default=[]),
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
            dt = datetime.fromisoformat(item["date_datetime"]) if item.get("date_datetime") else datetime.now()
            db.add(DateEntry(
                title=item.get("title", "Untitled Date"),
                pre_date_activities=item.get("pre_date_activities"),
                date_datetime=dt,
                duration_minutes=item.get("duration_minutes"),
                location_name=item.get("location_name"),
                location_lat=item.get("location_lat"),
                location_lon=item.get("location_lon"),
                what_we_did=item.get("what_we_did"),
                notes=item.get("notes"),
                rating=item.get("rating", 5),
            ))
            imported_dates += 1
        for item in data.get("comms", []):
            dt = datetime.fromisoformat(item["comm_datetime"]) if item.get("comm_datetime") else datetime.now()
            db.add(CommEntry(
                comm_datetime=dt,
                comm_type=item.get("comm_type", "Other"),
                description=item.get("description", ""),
            ))
            imported_comms += 1
        db.commit()
        return RedirectResponse(
            f"/dashboard?imported={imported_dates}&imported_comms={imported_comms}",
            status_code=302,
        )
    except Exception:
        return RedirectResponse("/dashboard?import_error=1", status_code=302)
