import os
import json
import io
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from .models import DateEntry

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Date-abase 💕")

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-love-key-change-me")
SHARED_PASSWORD = os.getenv("SHARED_PASSWORD", "lovebirds")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

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


def require_auth(request: Request):
    if not request.session.get("authenticated"):
        return False
    return True


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
    return templates.TemplateResponse("splash.html", {"request": request, "error": "Wrong password, babe. Try again. 💔"})


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
    return templates.TemplateResponse("dashboard.html", {"request": request, "dates": dates})


# ── Date CRUD ─────────────────────────────────────────────────────────────────

@app.get("/dates/new", response_class=HTMLResponse)
async def new_date_form(request: Request):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("date_form.html", {"request": request, "entry": None, "error": None})


@app.post("/dates/new")
async def create_date(
    request: Request,
    title: str = Form(...),
    pre_date_activities: str = Form(""),
    date_datetime: str = Form(...),
    duration_minutes: str = Form(""),
    location_name: str = Form(""),
    location_lat: str = Form(""),
    location_lon: str = Form(""),
    what_we_did: str = Form(""),
    notes: str = Form(""),
    rating: int = Form(5),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    try:
        dt = datetime.fromisoformat(date_datetime)
    except ValueError:
        return templates.TemplateResponse("date_form.html", {
            "request": request, "entry": None,
            "error": "Invalid date format. Let's try that again! 📅"
        })

    entry = DateEntry(
        title=title,
        pre_date_activities=pre_date_activities or None,
        date_datetime=dt,
        duration_minutes=int(duration_minutes) if duration_minutes else None,
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
    return RedirectResponse(f"/dates/{entry.id}", status_code=302)


@app.get("/dates/{entry_id}", response_class=HTMLResponse)
async def view_date(request: Request, entry_id: int, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(DateEntry).filter(DateEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    return templates.TemplateResponse("date_detail.html", {"request": request, "entry": entry})


@app.get("/dates/{entry_id}/edit", response_class=HTMLResponse)
async def edit_date_form(request: Request, entry_id: int, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(DateEntry).filter(DateEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    return templates.TemplateResponse("date_form.html", {"request": request, "entry": entry, "error": None})


@app.post("/dates/{entry_id}/edit")
async def update_date(
    request: Request,
    entry_id: int,
    title: str = Form(...),
    pre_date_activities: str = Form(""),
    date_datetime: str = Form(...),
    duration_minutes: str = Form(""),
    location_name: str = Form(""),
    location_lat: str = Form(""),
    location_lon: str = Form(""),
    what_we_did: str = Form(""),
    notes: str = Form(""),
    rating: int = Form(5),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(DateEntry).filter(DateEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Date not found 💔")
    try:
        dt = datetime.fromisoformat(date_datetime)
    except ValueError:
        return templates.TemplateResponse("date_form.html", {
            "request": request, "entry": entry,
            "error": "Invalid date format. 📅"
        })

    entry.title = title
    entry.pre_date_activities = pre_date_activities or None
    entry.date_datetime = dt
    entry.duration_minutes = int(duration_minutes) if duration_minutes else None
    entry.location_name = location_name or None
    entry.location_lat = float(location_lat) if location_lat else None
    entry.location_lon = float(location_lon) if location_lon else None
    entry.what_we_did = what_we_did or None
    entry.notes = notes or None
    entry.rating = rating
    db.commit()
    return RedirectResponse(f"/dates/{entry_id}", status_code=302)


@app.post("/dates/{entry_id}/delete")
async def delete_date(request: Request, entry_id: int, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    entry = db.query(DateEntry).filter(DateEntry.id == entry_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return RedirectResponse("/dashboard", status_code=302)


# ── Magic 8-Ball ──────────────────────────────────────────────────────────────

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
    data = {
        "export_date": datetime.now().isoformat(),
        "app": "Date-abase 💕",
        "dates": [d.to_dict() for d in dates],
    }
    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dateabase-export.json"},
    )


@app.post("/import")
async def import_data(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/", status_code=302)
    try:
        contents = await file.read()
        data = json.loads(contents)
        imported = 0
        for item in data.get("dates", []):
            dt = datetime.fromisoformat(item["date_datetime"]) if item.get("date_datetime") else datetime.now()
            entry = DateEntry(
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
            )
            db.add(entry)
            imported += 1
        db.commit()
        return RedirectResponse(f"/dashboard?imported={imported}", status_code=302)
    except Exception as e:
        return RedirectResponse("/dashboard?import_error=1", status_code=302)
