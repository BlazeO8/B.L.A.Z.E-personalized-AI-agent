"""
B.L.A.Z.E — Web Server
Wraps the existing blaze.py AI core and exposes it via FastAPI.
Run:  python blaze_server.py
Then open:  http://localhost:8000  (or http://YOUR_IP:8000 on phone)
"""

import sys, os, threading, datetime, re, json
sys.path.insert(0, os.path.dirname(__file__))

# ── FastAPI & WebSocket ────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("\n[BLAZE] FastAPI not found. Run:  pip install fastapi uvicorn\n")
    sys.exit(1)

# ── Import BLAZE core (from the blaze package submodules) ────────────────────
import platform

from blaze.config              import GROQ_API_KEY, MODEL
from blaze.core.database       import db
from blaze.core.logging_audit  import log
from blaze.deps                import psutil_available, voice_available
from blaze.ai.engine           import BlazeAI
from blaze.ai.persona          import persona
from blaze.intelligence.nlp       import nlp
from blaze.intelligence.emotional  import ei
from blaze.intelligence.learner    import learner
from blaze.services.system_monitor import (
    monitor, weather, news_module, filemanager, launcher, ReminderEngine,
)
from blaze.services.integrations import services
from blaze.plugins.manager     import plugins
from blaze.proactive.monitor   import ProactiveMonitor

_reminder_engine_ref = None  # set after server init

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="B.L.A.Z.E API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Extra middleware to handle file:// (null) origin — browsers send Origin: null
# for pages opened from disk, which '*' does NOT cover per the CORS spec.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class NullOriginCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        origin = request.headers.get("origin", "")
        response = await call_next(request)
        if origin == "null" or not origin:
            response.headers["Access-Control-Allow-Origin"]  = "*"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
        return response

app.add_middleware(NullOriginCORSMiddleware)

# ── Init AI core ───────────────────────────────────────────────────────────────
ai = BlazeAI()

# Init reminder engine and wire it up
def _on_reminder_web(message):
    """Push reminder to all connected WebSocket clients."""
    _broadcast({"type": "reminder", "text": message})

reminder_engine = ReminderEngine(_on_reminder_web)
ai._reminder_engine = reminder_engine

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()

import asyncio

def _broadcast(data: dict):
    """Thread-safe broadcast from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop)
    except Exception as e:
        log.warning(f"Broadcast error: {e}")

# Proactive monitor → push alerts/suggestions to browser
def _on_proactive(ptype, data):
    if ptype == "alert":
        _broadcast({"type": "alert", "text": data})
    elif ptype == "suggestion":
        _broadcast({"type": "suggestion", "text": data})
    elif ptype == "briefing":
        threading.Thread(target=_deliver_briefing, daemon=True).start()

def _deliver_briefing():
    w        = weather.summary_str()
    h        = news_module.get_headlines(3)
    news_str = "; ".join(h[:3]) if h else "News unavailable."
    sys_str  = monitor.summary()
    brief    = (f"Good morning, sir. Here is your daily briefing. "
                f"Weather: {w}. Top news: {news_str}. System: {sys_str}.")
    _broadcast({"type": "blaze", "text": brief})
    ai.speak(brief)

proactive = ProactiveMonitor(_on_proactive)

# ── Pydantic models ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class FeedbackRequest(BaseModel):
    rating: int  # 1-5

class ReminderRequest(BaseModel):
    message: str
    time: str   # HH:MM

class NoteRequest(BaseModel):
    title: str
    content: str

class SettingsRequest(BaseModel):
    user_name: str | None = None
    tone: str | None = None
    verbosity: str | None = None
    tts_speed: int | None = None
    city: str | None = None

class CommandRequest(BaseModel):
    trigger: str
    response: str
    action: str = ""

# ── Serve web UI ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    ui_path = os.path.join(os.path.dirname(__file__), "blaze_ui.html")
    if os.path.exists(ui_path):
        with open(ui_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>blaze_ui.html not found — place it in the same folder.</h1>", status_code=404)

# ── WebSocket — real-time chat ─────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg  = data.get("message", "").strip()
            if not msg:
                continue

            # NLP emotion for UI
            nlp_result = nlp.analyze(msg)
            emotion    = nlp_result.get("emotion", "neutral")
            mood_tag   = ei.mood_tag(emotion)

            # Echo emotion to client
            if mood_tag:
                await websocket.send_json({"type": "emotion", "text": f"{emotion} {mood_tag}"})

            # Stream "thinking" indicator
            await websocket.send_json({"type": "thinking"})

            try:
                # Run chat in thread (blocking Groq call)
                loop = asyncio.get_event_loop()
                reply = await loop.run_in_executor(None, ai.chat, msg)

                # Execute any system commands
                sys_results = await loop.run_in_executor(None, ai.execute_system_commands, reply)

                # Send reply
                clean = re.sub(r"\[SYSTEM:[^\]]+\]", "", reply)
                clean = re.sub(r"[*_`]", "", clean).strip()
                await websocket.send_json({"type": "blaze", "text": clean})

                # Send system command results
                for r in sys_results:
                    await websocket.send_json({"type": "system", "text": r})

                # TTS
                threading.Thread(target=ai.speak, args=(reply,), daemon=True).start()

            except Exception as e:
                log.error(f"WebSocket chat error: {e}")
                await websocket.send_json({"type": "error", "text": f"Neural core error: {e}"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)

# ── REST endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """System status — used by the dashboard."""
    bat = monitor.battery() if psutil_available else None
    return {
        "online":     bool(GROQ_API_KEY),
        "model":      MODEL,
        "platform":   f"{platform.system()} {platform.release()}",
        "cpu":        round(monitor.cpu(), 1)     if psutil_available else 0,
        "ram":        round(monitor.ram(), 1)     if psutil_available else 0,
        "disk":       round(monitor.disk(), 1)    if psutil_available else 0,
        "battery":    bat,
        "voice":      voice_available,
        "name":       persona.name,
        "time":       datetime.datetime.now().strftime("%H:%M:%S"),
        "date":       datetime.datetime.now().strftime("%A, %B %d %Y"),
    }

@app.get("/api/weather")
async def get_weather():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, weather.get)
    return data

@app.get("/api/reminders")
async def get_reminders():
    rows = db.get_all_reminders()
    return [{"id": r[0], "message": r[1], "fire_at": r[2]} for r in rows]

@app.post("/api/reminders")
async def add_reminder(req: ReminderRequest):
    try:
        h, mi = map(int, req.time.split(":"))
        fire  = datetime.datetime.now().replace(hour=h, minute=mi, second=0, microsecond=0)
        if fire < datetime.datetime.now():
            fire += datetime.timedelta(days=1)
        db.add_reminder(req.message, fire)
        return {"status": "ok", "message": f"Reminder set for {fire.strftime('%I:%M %p')}"}
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@app.get("/api/news")
async def get_news():
    loop = asyncio.get_event_loop()
    headlines = await loop.run_in_executor(None, news_module.get_headlines, 8)
    return {"headlines": headlines or []}

@app.post("/api/feedback")
async def save_feedback(req: FeedbackRequest):
    msg = ai.save_feedback(req.rating)
    return {"status": "ok", "message": msg}

@app.get("/api/history")
async def get_history():
    rows = db.fetchall(
        "SELECT role, content, emotion, ts FROM conversations ORDER BY id DESC LIMIT 50"
    )
    return [{"role": r[0], "content": r[1], "emotion": r[2], "ts": r[3]} for r in reversed(rows)]

@app.delete("/api/history")
async def clear_history():
    db.clear_history()
    ai.history.clear()
    return {"status": "ok"}

@app.get("/api/settings")
async def get_settings():
    return {
        "user_name": persona.name,
        "tone":      persona.tone,
        "verbosity": persona.verbosity,
        "tts_speed": persona.tts_speed,
        "city":      db.get_pref("BLAZE_CITY", "Delhi"),
        "voice":     ai.voice_enabled,
    }

@app.post("/api/settings")
async def save_settings(req: SettingsRequest):
    if req.user_name: persona.name      = req.user_name; db.set_pref("user_name", req.user_name)
    if req.tone:      persona.tone      = req.tone;      db.set_pref("tone", req.tone)
    if req.verbosity: persona.verbosity = req.verbosity; db.set_pref("verbosity", req.verbosity)
    if req.tts_speed: persona.tts_speed = req.tts_speed; db.set_pref("tts_speed", str(req.tts_speed))
    if req.city:      db.set_pref("BLAZE_CITY", req.city)
    persona.save()
    return {"status": "ok"}

@app.get("/api/stats")
async def get_stats():
    top_cmds = db.get_top_commands(8)
    avg      = db.get_avg_rating()
    habits   = db.get_top_habits(5)
    return {
        "top_commands": [{"command": c, "count": n} for c, n in top_cmds],
        "avg_rating":   avg,
        "habits":       [{"pattern": p, "frequency": f} for p, f in habits],
        "summary":      monitor.summary() if psutil_available else "psutil not installed",
    }

@app.post("/api/commands")
async def add_custom_command(req: CommandRequest):
    db.add_custom_command(req.trigger, req.response, req.action)
    return {"status": "ok"}

@app.get("/api/commands")
async def list_commands():
    rows = db.get_custom_commands()
    return [{"trigger": r[0], "response": r[1], "action": r[2]} for r in rows]

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket
    host = "0.0.0.0"
    port = 8000
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"""
╔══════════════════════════════════════════════════════╗
║          B . L . A . Z . E  —  Web Server            ║
╠══════════════════════════════════════════════════════╣
║  Desktop  →  http://localhost:{port}                 ║
║  Phone    →  http://{local_ip}:{port}                ║
║  (Same Wi-Fi required for phone access)              ║
╚══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host=host, port=port, log_level="warning")