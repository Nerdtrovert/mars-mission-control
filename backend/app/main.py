import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import router, active_runner, simulator_runner, storage, dashboard_broadcaster

# Frontend directory resolution
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path("frontend").resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register the running event loop for safe background broadcasting
    dashboard_broadcaster.set_loop(asyncio.get_running_loop())

    # Managed startup: begin active gateway runner (simulator or network)
    await active_runner.start()

    # Continuous background telemetry retention cleaner (runs in all modes)
    async def _retention_loop():
        while True:
            try:
                await asyncio.sleep(5.0)
                storage.prune_telemetry(retention_seconds=300.0)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    retention_task = asyncio.create_task(_retention_loop(), name="telemetry_retention_cleaner")

    try:
        yield
    finally:
        # Managed shutdown: cancel and await clean completion
        retention_task.cancel()
        try:
            await retention_task
        except asyncio.CancelledError:
            pass
        await active_runner.stop()


app = FastAPI(
    title="Mars Mission Control",
    description="Backend API for the Mars Lander mission control system.",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def add_cache_control_headers(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/dashboard":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Mount static frontend assets
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

app.include_router(router)


@app.get("/")
async def root():
    return {
        "application": "Mars Mission Control",
        "status": "online",
        "version": "1.0.0",
        "simulation_mode": getattr(active_runner, "IS_SIMULATOR", True),
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "simulation_mode": getattr(active_runner, "IS_SIMULATOR", True),
    }


@app.get("/dashboard")
async def get_dashboard():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return {"error": "Dashboard frontend not installed"}
    return FileResponse(
        str(index_file),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
