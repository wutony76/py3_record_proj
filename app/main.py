from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .core.config import SCREENSHOT_DIR
from .services import screenshot

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await screenshot.start_browser()
    yield
    await screenshot.stop_browser()


app = FastAPI(title="py3_record_proj", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/data/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
