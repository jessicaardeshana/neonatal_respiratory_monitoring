"""FastAPI server for the interactive demo. Binds to 127.0.0.1 only; nothing leaves the machine.

Endpoints (all demo data is SIMULATED):
    GET  /api/health          liveness + version
    GET  /api/schema          slider definitions + default parameters
    POST /api/run             run a scenario through the real pipeline -> all stage data
    GET  /api/frames          thermal frames as raw int16 (centi-degC), in chunks
    GET  /api/spectrum        amplitude spectrum before/after band-pass over a time range
    GET  /api/window          what the rate estimator sees for the window ending at t_end
    GET  /api/results         report tables and the honest-limits list
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from thermal import __version__
from thermal.app.results import load_results
from thermal.app.scenarios import PRESETS, SCHEMA, ScenarioParams
from thermal.app.service import FRAME_COLS, FRAME_ROWS, Service

STATIC = Path(__file__).parent / "static"
MAX_FRAMES_PER_REQUEST = 256


def create_app(service: Service | None = None) -> FastAPI:
    app = FastAPI(title="Thermal Respiratory Sensing: Proof of Concept", version=__version__)
    svc = service or Service()
    app.state.service = svc

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "mode": "simulation"}

    @app.get("/api/schema")
    def schema() -> dict:
        return {"controls": SCHEMA, "defaults": ScenarioParams().model_dump(), "presets": PRESETS}

    @app.post("/api/run")
    def run(params: ScenarioParams) -> dict:
        return svc.run(params).payload

    @app.get("/api/frames")
    def frames(run: str, start: int = Query(0, ge=0), count: int = Query(64, ge=1)) -> Response:
        r = svc.get(run)
        if r is None:
            raise HTTPException(404, "Unknown or expired run. Run the scenario again.")
        count = min(count, MAX_FRAMES_PER_REQUEST)
        chunk = r.frames_i16[start : start + count]
        if chunk.shape[0] == 0:
            raise HTTPException(416, "Frame range is past the end of the recording.")
        return Response(chunk.astype("<i2").tobytes(), media_type="application/octet-stream",
                        headers={"X-Frame-Count": str(chunk.shape[0]), "X-Frame-Rows": str(FRAME_ROWS),
                                 "X-Frame-Cols": str(FRAME_COLS), "X-Frame-Scale": "0.01",
                                 "Cache-Control": "no-store"})

    def _need(run_id: str):
        r = svc.get(run_id)
        if r is None:
            raise HTTPException(404, "Unknown or expired run. Run the scenario again.")
        return r

    @app.get("/api/spectrum")
    def spectrum(run: str, t0: float = Query(..., ge=0), t1: float = Query(..., ge=0)) -> dict:
        r = _need(run)
        try:
            return svc.spectrum(r, t0, t1)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/window")
    def window(run: str, t_end: float = Query(..., ge=0)) -> dict:
        r = _need(run)
        try:
            return svc.window(r, t_end)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/results")
    def results() -> dict:
        return load_results()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
