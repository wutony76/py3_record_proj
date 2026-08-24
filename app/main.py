from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .services import screenshot


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
