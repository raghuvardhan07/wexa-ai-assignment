"""Repository functions — thin wrappers around parameterized Cypher queries."""
from neo4j import Session

from cascade import db
from cascade.queries import (
    AGENTS_FOR_TASKS,
    ALL_GOALS,
    ALL_TOOLS,
    BLAST_RADIUS,
    BLOCKED_GOALS,
    COUNT_AGENTS,
    COUNT_GOALS_BLOCKED,
    COUNT_GOALS_COMPLETE,
    COUNT_GOALS_TOTAL,
    COUNT_TOOLS_OFFLINE,
    COUNT_TOOLS_ONLINE,
    CRITICAL_PATH,
    GOAL_COMPOSITION_TASKS,
    SET_TOOL_STATUS,
    TASK_DEPENDENCIES,
    TOOL_USAGE,
    TOOLS_FOR_TASKS,
)


def _tool_map(session: Session, task_ids: list[str]) -> dict[str, str | None]:
    if not task_ids:
        return {}
    rows = db._run(session, TOOLS_FOR_TASKS, task_ids=task_ids)
    return {r["task_id"]: r["tool_name"] for r in rows}


def get_health_counts(session: Session) -> dict:
    online = db._one(session, COUNT_TOOLS_ONLINE)
    offline = db._one(session, COUNT_TOOLS_OFFLINE)
    total_goals = db._one(session, COUNT_GOALS_TOTAL)
    complete = db._one(session, COUNT_GOALS_COMPLETE)
    blocked = db._one(session, COUNT_GOALS_BLOCKED)
    return {
        "tools": {"online": online, "offline": offline, "total": online + offline},
        "agents": {"total": db._one(session, COUNT_AGENTS)},
        "goals": {
            "total": total_goals,
            "complete": complete,
            "blocked": blocked,
            "active": total_goals - complete - blocked,
        },
    }


def get_blocked_goals(session: Session) -> list[dict]:
    """Return one row per blocked goal: the shortest failure chain."""
    rows = db._run(session, BLOCKED_GOALS)
    best: dict[str, dict] = {}
    for r in rows:
        gid = r["goal_id"]
        if gid not in best or r["hops"] < best[gid]["hops"]:
            best[gid] = r
    return list(best.values())


def get_blast_radius(session: Session, tool_id: str) -> dict:
    rows = db._run(session, BLAST_RADIUS, tool_id=tool_id)
    best: dict[str, dict] = {}
    for r in rows:
        gid = r["goal_id"]
        if gid not in best or r["hops"] < best[gid]["hops"]:
            best[gid] = r

    all_task_ids = [node["id"] for b in best.values() for node in b["failure_chain"]]
    tools = _tool_map(session, all_task_ids)

    blocked = []
    for b in best.values():
        blocked.append({
            "goal_id": b["goal_id"],
            "goal_name": b["goal_name"],
            "root_cause_tool_id": b["root_cause_tool_id"],
            "root_cause_tool": b["root_cause_tool"],
            "root_cause_kind": b["root_cause_kind"],
            "failing_step": b["failing_step"],
            "failure_chain": [
                {"name": node["name"], "tool": tools.get(node["id"])}
                for node in b["failure_chain"]
            ],
            "hops": b["hops"],
        })
    return {"tool_id": tool_id, "count": len(blocked), "blocked_goals": blocked}


def get_critical_path(session: Session, goal_id: str) -> dict:
    row = db._run(session, CRITICAL_PATH, goal_id=goal_id)
    if not row:
        return {
            "goal_id": goal_id,
            "predicted_latency_ms": 0,
            "critical_path": [],
            "bottleneck": None,
        }
    tasks = row[0]["critical_path_tasks"]
    task_ids = [t["id"] for t in tasks]
    agents = db._run(session, AGENTS_FOR_TASKS, task_ids=task_ids)
    agent_map = {a["task_id"]: a for a in agents}
    tools = _tool_map(session, task_ids)
    bottleneck = max(tasks, key=lambda t: t["estimated_ms"]) if tasks else None
    return {
        "goal_id": goal_id,
        "predicted_latency_ms": row[0]["predicted_latency_ms"],
        "critical_path": [
            {
                "id": t["id"],
                "name": t["name"],
                "estimated_ms": t["estimated_ms"],
                "agent": agent_map.get(t["id"], {}).get("agent_name"),
                "tool": tools.get(t["id"]),
            }
            for t in tasks
        ],
        "bottleneck": {
            "id": bottleneck["id"],
            "name": bottleneck["name"],
            "estimated_ms": bottleneck["estimated_ms"],
        } if bottleneck else None,
    }


def set_tool_status(session: Session, tool_id: str, status: str) -> dict | None:
    rows = db._run(session, SET_TOOL_STATUS, tool_id=tool_id, status=status)
    return rows[0] if rows else None


def get_tools(session: Session) -> list[dict]:
    return db._run(session, ALL_TOOLS)


def get_goals(session: Session) -> list[dict]:
    return db._run(session, ALL_GOALS)


def get_goal_composition(session: Session, goal_id: str) -> list[dict]:
    tasks = db._run(session, GOAL_COMPOSITION_TASKS, goal_id=goal_id)
    task_ids = [t["task_id"] for t in tasks]
    dep_rows = db._run(session, TASK_DEPENDENCIES, task_ids=task_ids) if task_ids else []
    dep_map: dict[str, list[str]] = {}
    for d in dep_rows:
        dep_map.setdefault(d["task_id"], []).append(d["parent_id"])
    for t in tasks:
        t["depends_on"] = dep_map.get(t["task_id"], [])
    return tasks


def get_tool_usage(session: Session, tool_id: str) -> list[dict]:
    return db._run(session, TOOL_USAGE, tool_id=tool_id)
