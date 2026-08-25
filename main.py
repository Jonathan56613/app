"""
Éclair Live - backend
----------------------
Se connecte en continu au flux temps réel du réseau communautaire
Blitzortung.org (wss://ws1.blitzortung.org), décode les impacts de
foudre reçus, les garde en mémoire pendant quelques heures, et les
expose via une petite API REST + sert la page web statique.

Aucune clé API n'est nécessaire : Blitzortung est un réseau ouvert et
gratuit alimenté par des bénévoles.
"""

import asyncio
import json
import math
import time
from collections import deque
from contextlib import asynccontextmanager

import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

BLITZORTUNG_WS_URL = "wss://ws1.blitzortung.org/"
MAX_RETENTION_HOURS = 3.5  # un peu de marge au-dessus des 3h demandées
MAX_STRIKES_KEPT = 40_000  # garde-fou mémoire
DEFAULT_RESULT_LIMIT = 500

# --------------------------------------------------------------------------
# Stockage en mémoire des impacts récents
# --------------------------------------------------------------------------

strikes: deque = deque(maxlen=MAX_STRIKES_KEPT)
connection_status = {"connected": False, "last_error": None, "last_strike_at": None}


def decode_blitzortung_frame(raw: bytes) -> bytes:
    """Décode le flux (compression type LZW) utilisé par le websocket
    public de Blitzortung pour transformer les octets reçus en JSON brut."""
    text = list(raw.decode("utf-8"))
    dictionary = {}
    current = text[0]
    result = [current]
    prev = current
    next_code = 256
    for i in range(1, len(text)):
        code_point = ord(text[i])
        if code_point < 256:
            entry = text[i]
        elif code_point in dictionary:
            entry = dictionary[code_point]
        else:
            entry = prev + current
        result.append(entry)
        current = entry[0]
        dictionary[next_code] = prev + current
        next_code += 1
        prev = entry
    return "".join(result).encode("utf-8")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def prune_old_strikes():
    cutoff = time.time() - MAX_RETENTION_HOURS * 3600
    while strikes and strikes[0]["ts"] < cutoff:
        strikes.popleft()


# --------------------------------------------------------------------------
# Tâche de fond : écoute permanente du flux Blitzortung, avec reconnexion
# --------------------------------------------------------------------------

async def blitzortung_listener():
    backoff = 2
    while True:
        try:
            async with websockets.connect(BLITZORTUNG_WS_URL, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"a": 111}))
                connection_status["connected"] = True
                connection_status["last_error"] = None
                backoff = 2
                async for message in ws:
                    try:
                        raw = message if isinstance(message, (bytes, bytearray)) else message.encode("utf-8")
                        decoded = decode_blitzortung_frame(raw)
                        data = json.loads(decoded)
                        lat = data.get("lat")
                        lon = data.get("lon")
                        t_ns = data.get("time")
                        if lat is None or lon is None or t_ns is None:
                            continue
                        strikes.append({"lat": lat, "lon": lon, "ts": t_ns / 1_000_000_000})
                        connection_status["last_strike_at"] = time.time()
                    except Exception:
                        # une trame illisible ne doit jamais casser la boucle
                        continue
        except Exception as exc:
            connection_status["connected"] = False
            connection_status["last_error"] = str(exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(blitzortung_listener())
    yield
    task.cancel()


app = FastAPI(title="Éclair Live", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    prune_old_strikes()
    return {
        "connected": connection_status["connected"],
        "last_error": connection_status["last_error"],
        "strikes_in_memory": len(strikes),
    }


@app.get("/api/strikes")
def api_strikes(
    hours: float = Query(3.0, ge=0.05, le=MAX_RETENTION_HOURS),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    max_km: float | None = Query(None, description="ne renvoie que les impacts dans ce rayon"),
    limit: int = Query(DEFAULT_RESULT_LIMIT, le=5000),
):
    prune_old_strikes()
    cutoff = time.time() - hours * 3600
    now = time.time()

    results = []
    for s in strikes:
        if s["ts"] < cutoff:
            continue
        item = {
            "lat": s["lat"],
            "lon": s["lon"],
            "age_sec": max(0, now - s["ts"]),
        }
        if lat is not None and lon is not None:
            dist = haversine_km(lat, lon, s["lat"], s["lon"])
            if max_km is not None and dist > max_km:
                continue
            item["distance_km"] = round(dist, 2)
        results.append(item)

    if lat is not None and lon is not None:
        results.sort(key=lambda x: x["distance_km"])
    else:
        results.sort(key=lambda x: x["age_sec"])

    return {"count": len(results), "strikes": results[:limit]}


# --------------------------------------------------------------------------
# Frontend statique
# --------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
