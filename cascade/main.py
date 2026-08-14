from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

from cascade import db, repo
from cascade.config import get_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    db.close_driver()


app = FastAPI(
    title="CASCADE — Agentic Workflow Blast-Radius Explorer",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(ServiceUnavailable)
async def _db_unavailable(_, __: ServiceUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "db_unreachable", "message": "Unable to reach CognoDB instance."}},
    )


@app.exception_handler(AuthError)
async def _db_auth(_, __: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "db_auth_failed", "message": "Unable to authenticate to CognoDB. Check COGNODB_PASSWORD."}},
    )


@app.exception_handler(Neo4jError)
async def _db_query(_, __: Neo4jError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "db_query_error", "message": "The graph query failed."}},
    )


def _needs_db() -> None:
    if not db.ping():
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unreachable", "message": "Unable to reach CognoDB instance."},
        )


@app.get("/api/healthz")
def healthz() -> dict:
    return {"db": "ok" if db.ping() else "unreachable"}


@app.get("/api/system")
def system() -> dict:
    _needs_db()
    with db.db_session() as s:
        return {
            "counts": repo.get_health_counts(s),
            "tools": repo.get_tools(s),
            "goals": repo.get_goals(s),
            "blocked_goals": repo.get_blocked_goals(s),
        }


@app.get("/api/blast-radius")
def blast_radius(tool_id: str = Query(...)) -> dict:
    _needs_db()
    with db.db_session() as s:
        return repo.get_blast_radius(s, tool_id)


@app.get("/api/critical-path")
def critical_path(goal_id: str = Query(...)) -> dict:
    _needs_db()
    with db.db_session() as s:
        return repo.get_critical_path(s, goal_id)


@app.get("/api/goals/{goal_id}/composition")
def goal_composition(goal_id: str) -> list[dict]:
    _needs_db()
    with db.db_session() as s:
        return repo.get_goal_composition(s, goal_id)


@app.get("/api/tools/{tool_id}/usage")
def tool_usage(tool_id: str) -> list[dict]:
    _needs_db()
    with db.db_session() as s:
        return repo.get_tool_usage(s, tool_id)


@app.post("/api/tools/{tool_id}/status")
def set_tool_status(tool_id: str, status: str = Query(...)) -> dict:
    if status not in ("ONLINE", "OFFLINE"):
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_status", "message": "status must be ONLINE or OFFLINE."},
        )
    _needs_db()
    with db.db_session() as s:
        result = repo.set_tool_status(s, tool_id, status)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Tool not found."},
        )
    return result


# Static UI
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run("cascade.main:app", host=s.api_host, port=s.api_port, reload=False)


if __name__ == "__main__":
    main()
