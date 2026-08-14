from cascade import db
from cascade.queries import CONSTRAINTS, WIPE

TOOLS = [
    {"id": "web_search",  "name": "Web Search API",          "kind": "SEARCH", "status": "ONLINE"},
    {"id": "github",      "name": "GitHub API",              "kind": "HTTP",   "status": "OFFLINE"},
    {"id": "vector_db",   "name": "Vector Store",            "kind": "VECTOR", "status": "ONLINE"},
    {"id": "python_repl", "name": "Python Code Interpreter", "kind": "CODE",   "status": "ONLINE"},
    {"id": "slack",       "name": "Slack API",               "kind": "HTTP",   "status": "ONLINE"},
    {"id": "stripe",      "name": "Stripe API",              "kind": "HTTP",   "status": "OFFLINE"},
    {"id": "s3",          "name": "S3 Storage",              "kind": "DB",     "status": "ONLINE"},
    {"id": "sql_db",      "name": "Customer SQL DB",         "kind": "DB",     "status": "ONLINE"},
]

AGENTS = [
    {"id": "researcher", "name": "Research-Agent", "model": "gpt-4o"},
    {"id": "coder",      "name": "Coder-Agent",    "model": "claude-3-5-sonnet"},
    {"id": "writer",     "name": "Writer-Agent",   "model": "gpt-4o-mini"},
    {"id": "reviewer",   "name": "Reviewer-Agent", "model": "claude-3-5-sonnet"},
    {"id": "planner",    "name": "Planner-Agent",  "model": "gpt-4o"},
]

# Each goal is: (goal_dict, root_name, [single_intermediate], [leaves]).
# Leaves are (task_name, tool_id, agent_id, estimated_ms).
# The DAG is always: Goal → Root → Intermediate → Leaves → Tools.
GOALS = [
    (
        {"id": "market_report", "name": "Generate Q3 Market Intelligence Report"},
        "Generate Q3 market report",
        ["Draft executive summary"],
        [
            ("Search competitor news", "web_search", "researcher", 1200),
            ("Pull SEC filings", "github", "researcher", 2000),
            ("Query market vectors", "vector_db", "researcher", 900),
            ("Generate charts", "python_repl", "coder", 1500),
        ],
    ),
    (
        {"id": "code_audit", "name": "Automated Code Audit of PR #402"},
        "Compile PR audit report",
        ["Review changed files"],
        [
            ("Fetch PR diff", "github", "coder", 800),
            ("Run static analysis", "python_repl", "coder", 1800),
            ("Check dependency CVEs", "sql_db", "reviewer", 1400),
        ],
    ),
    (
        {"id": "security_scan", "name": "Weekly Security Vulnerability Scan"},
        "Publish vulnerability summary",
        ["Score findings"],
        [
            ("List cloud buckets", "s3", "planner", 1000),
            ("Query vulnerability DB", "sql_db", "reviewer", 1200),
            ("Correlate with code repos", "github", "coder", 1600),
        ],
    ),
    (
        {"id": "invoice_recon", "name": "Reconcile Stripe Invoices vs Internal Ledger"},
        "Produce reconciliation statement",
        ["Compare amounts"],
        [
            ("List Stripe invoices", "stripe", "coder", 1500),
            ("Query ledger rows", "sql_db", "researcher", 1100),
            ("Notify finance channel", "slack", "writer", 600),
        ],
    ),
    (
        {"id": "onboarding", "name": "Auto-Generate New Hire Onboarding Pack"},
        "Deliver onboarding pack",
        ["Personalize content"],
        [
            ("Find handbook pages", "vector_db", "researcher", 900),
            ("Pull org chart", "github", "planner", 700),
            ("Generate welcome email", "slack", "writer", 500),
        ],
    ),
]


def _build_goal(goal, root_name, intermediates, leaves):
    goal["status"] = "ACTIVE"
    gid = goal["id"]

    tasks = []
    depends_on = []
    requires = []
    assigned_to = []
    has_task = {"goal_id": gid, "task_id": f"{gid}_root"}

    # Root task
    root_id = f"{gid}_root"
    tasks.append({"id": root_id, "name": root_name, "status": "PENDING", "estimated_ms": 800})
    assigned_to.append({"task_id": root_id, "agent_id": "planner"})

    # Intermediate layer: root depends on each intermediate.
    prev_layer = [root_id]
    for i, name in enumerate(intermediates):
        tid = f"{gid}_mid_{i}"
        tasks.append({"id": tid, "name": name, "status": "PENDING", "estimated_ms": 600})
        depends_on.append({"from": prev_layer[0], "to": tid})
        assigned_to.append({"task_id": tid, "agent_id": "reviewer"})
    prev_layer = [f"{gid}_mid_{i}" for i in range(len(intermediates))]

    # Leaves: each intermediate depends on one leaf. Leaves require a tool.
    for i, (name, tool_id, agent_id, estimated_ms) in enumerate(leaves):
        tid = f"{gid}_leaf_{i}"
        tasks.append({"id": tid, "name": name, "status": "PENDING", "estimated_ms": estimated_ms})
        depends_on.append({"from": prev_layer[i % len(prev_layer)], "to": tid})
        requires.append({"task_id": tid, "tool_id": tool_id})
        assigned_to.append({"task_id": tid, "agent_id": agent_id})

    return goal, tasks, depends_on, requires, assigned_to, has_task


def build_dataset():
    goals, all_tasks, all_depends, all_requires, all_assigned, all_has_task = [], [], [], [], [], []
    for goal_def in GOALS:
        g, tasks, depends, requires, assigned, has_task = _build_goal(*goal_def)
        goals.append(g)
        all_tasks.extend(tasks)
        all_depends.extend(depends)
        all_requires.extend(requires)
        all_assigned.extend(assigned)
        all_has_task.append(has_task)
    return {
        "tools": TOOLS,
        "agents": AGENTS,
        "goals": goals,
        "tasks": all_tasks,
        "depends_on": all_depends,
        "requires": all_requires,
        "assigned_to": all_assigned,
        "has_task": all_has_task,
    }


def _bulk_insert(session, cypher, rows, batch=100):
    for i in range(0, len(rows), batch):
        session.run(cypher, rows=rows[i : i + batch]).consume()


def main():
    if not db.ping():
        raise RuntimeError(
            "Cannot reach CognoDB. Check COGNODB_URI, COGNODB_USERNAME, and COGNODB_PASSWORD."
        )

    dataset = build_dataset()

    with db.db_session() as s:
        s.run(WIPE).consume()
        for cypher in CONSTRAINTS:
            s.run(cypher).consume()

        _bulk_insert(s, """
            UNWIND $rows AS row
            CREATE (t:Tool {id: row.id, name: row.name, kind: row.kind, status: row.status})
        """, dataset["tools"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            CREATE (a:Agent {id: row.id, name: row.name, model: row.model})
        """, dataset["agents"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            CREATE (g:Goal {id: row.id, name: row.name, status: row.status})
        """, dataset["goals"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            CREATE (t:Task {id: row.id, name: row.name, status: row.status, estimated_ms: row.estimated_ms})
        """, dataset["tasks"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            MATCH (g:Goal {id: row.goal_id}), (t:Task {id: row.task_id})
            CREATE (g)-[:HAS_TASK]->(t)
        """, dataset["has_task"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            MATCH (a:Task {id: row.from}), (b:Task {id: row.to})
            CREATE (a)-[:DEPENDS_ON]->(b)
        """, dataset["depends_on"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            MATCH (t:Task {id: row.task_id}), (tool:Tool {id: row.tool_id})
            CREATE (t)-[:REQUIRES]->(tool)
        """, dataset["requires"])
        _bulk_insert(s, """
            UNWIND $rows AS row
            MATCH (t:Task {id: row.task_id}), (a:Agent {id: row.agent_id})
            CREATE (t)-[:ASSIGNED_TO]->(a)
        """, dataset["assigned_to"])

    db.close_driver()

    print("CASCADE seed complete:")
    print(f"  goals      {len(dataset['goals'])}")
    print(f"  tasks      {len(dataset['tasks'])}")
    print(f"  agents     {len(dataset['agents'])}")
    print(f"  tools      {len(dataset['tools'])}")
    print(f"  has_task   {len(dataset['has_task'])}")
    print(f"  depends_on {len(dataset['depends_on'])}")
    print(f"  requires   {len(dataset['requires'])}")


if __name__ == "__main__":
    main()
