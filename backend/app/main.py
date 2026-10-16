from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import CreateRunRequest, CreateRunResponse, RunState
from .store import store

app = FastAPI(title="Multi-Agent Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.dashboard_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_run_or_404(run_id: str) -> RunState:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return run


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/runs", status_code=202, response_model=CreateRunResponse)
async def create_run(body: CreateRunRequest) -> CreateRunResponse:
    run = store.create(body.query)
    return CreateRunResponse(run_id=run.run_id)


@app.get("/api/runs/{run_id}", response_model=RunState)
async def get_run(run_id: str) -> RunState:
    return _get_run_or_404(run_id)
