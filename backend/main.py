"""
Punkt wejścia FastAPI — API + statyczny frontend.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import auth, learning

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    (BASE_DIR / "data").mkdir(exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="LangApp LAN", version="1.0.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(learning.router)

app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
async def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard")
async def dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi import Response
    return Response(status_code=204)