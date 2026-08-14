"""All parameterized Cypher queries and schema constants."""

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CONSTRAINTS = [
    "CREATE CONSTRAINT goal_id  IF NOT EXISTS FOR (g:Goal)  REQUIRE g.id IS UNIQUE",
    "CREATE CONSTRAINT task_id  IF NOT EXISTS FOR (t:Task)  REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT tool_id  IF NOT EXISTS FOR (t:Tool)  REQUIRE t.id IS UNIQUE",
    "CREATE INDEX tool_status IF NOT EXISTS FOR (t:Tool) ON (t.status)",
]

WIPE = "MATCH (n) DETACH DELETE n"

# ---------------------------------------------------------------------------
# Hero queries
# ---------------------------------------------------------------------------

# Multi-hop blast radius: every goal blocked by an offline tool, with the
# shortest failure chain from goal down to the tool.
BLAST_RADIUS = """
MATCH (tool:Tool {id: $tool_id, status: 'OFFLINE'})<-[:REQUIRES]-(failedTask:Task)
MATCH p = (goal:Goal)-[:HAS_TASK]->(rootTask:Task)-[:DEPENDS_ON*0..4]->(failedTask)
WHERE goal.status <> 'COMPLETE'
RETURN
  goal.id AS goal_id,
  goal.name AS goal_name,
  tool.id AS root_cause_tool_id,
  tool.name AS root_cause_tool,
  tool.kind AS root_cause_kind,
  failedTask.id AS failing_step_id,
  failedTask.name AS failing_step,
  [n IN nodes(p) WHERE n:Task | {id: n.id, name: n.name}] AS failure_chain,
  length(p) + 1 AS hops
ORDER BY goal.name, hops
"""

# Weighted longest path through a goal's dependency DAG. Genuinely awkward in
# SQL: recursive CTE + running sum + argmax path reconstruction.
CRITICAL_PATH = """
MATCH (goal:Goal {id: $goal_id})-[:HAS_TASK]->(rootTask:Task)
MATCH p = (rootTask)-[:DEPENDS_ON*0..6]->(leafTask:Task)
WHERE NOT (leafTask)-[:DEPENDS_ON]->(:Task)
WITH p,
     reduce(total = 0, n IN nodes(p) | total + coalesce(n.estimated_ms, 0)) AS total_ms
ORDER BY total_ms DESC
LIMIT 1
RETURN
  total_ms AS predicted_latency_ms,
  [n IN nodes(p) | {id: n.id, name: n.name, estimated_ms: coalesce(n.estimated_ms, 0)}] AS critical_path_tasks
"""

# All currently blocked goals, derived from the graph rather than Goal.status.
BLOCKED_GOALS = """
MATCH (tool:Tool {status: 'OFFLINE'})<-[:REQUIRES]-(failedTask:Task)
MATCH p = (goal:Goal)-[:HAS_TASK]->(:Task)-[:DEPENDS_ON*0..4]->(failedTask)
WHERE goal.status <> 'COMPLETE'
RETURN
  goal.id AS goal_id,
  goal.name AS goal_name,
  tool.id AS root_cause_tool_id,
  tool.name AS root_cause_tool,
  tool.status AS root_cause_status,
  failedTask.name AS failing_step,
  [n IN nodes(p) WHERE n:Task | n.name] AS failure_chain,
  length(p) + 1 AS hops
ORDER BY goal.name, hops
"""

# System health counts.
COUNT_TOOLS_ONLINE = "MATCH (t:Tool {status: 'ONLINE'})  RETURN count(t) AS n"
COUNT_TOOLS_OFFLINE = "MATCH (t:Tool {status: 'OFFLINE'}) RETURN count(t) AS n"
COUNT_AGENTS = "MATCH (a:Agent) RETURN count(a) AS n"
COUNT_GOALS_TOTAL = "MATCH (g:Goal) RETURN count(g) AS n"
COUNT_GOALS_COMPLETE = "MATCH (g:Goal {status: 'COMPLETE'}) RETURN count(g) AS n"
COUNT_GOALS_BLOCKED = """
MATCH (tool:Tool {status: 'OFFLINE'})<-[:REQUIRES]-(f:Task)
MATCH (goal:Goal)-[:HAS_TASK]->(:Task)-[:DEPENDS_ON*0..4]->(f)
WHERE goal.status <> 'COMPLETE'
RETURN count(DISTINCT goal) AS n
"""

# Sidebar / lookup queries.
ALL_TOOLS = """
MATCH (t:Tool)
RETURN t.id AS id, t.name AS name, t.kind AS kind, t.status AS status
ORDER BY t.name
"""

ALL_GOALS = """
MATCH (g:Goal)
RETURN g.id AS id, g.name AS name, g.status AS status
ORDER BY g.name
"""

AGENTS_FOR_TASKS = """
MATCH (t:Task)-[:ASSIGNED_TO]->(a:Agent)
WHERE t.id IN $task_ids
RETURN t.id AS task_id, a.name AS agent_name, a.model AS agent_model
"""

TOOLS_FOR_TASKS = """
MATCH (t:Task)-[:REQUIRES]->(tool:Tool)
WHERE t.id IN $task_ids
RETURN t.id AS task_id, tool.name AS tool_name
"""

# Goal composition: all tasks reachable from a goal's root, with agent and tool.
GOAL_COMPOSITION_TASKS = """
MATCH (g:Goal {id: $goal_id})-[:HAS_TASK]->(root:Task)
MATCH (root)-[:DEPENDS_ON*0..6]->(t:Task)
OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(a:Agent)
OPTIONAL MATCH (t)-[:REQUIRES]->(tool:Tool)
RETURN t.id AS task_id,
       t.name AS task_name,
       t.estimated_ms AS estimated_ms,
       a.name AS agent_name,
       tool.id AS tool_id,
       tool.name AS tool_name,
       tool.status AS tool_status,
       (t.id = root.id) AS is_root
ORDER BY t.name
"""

# Parent IDs for a set of tasks.
TASK_DEPENDENCIES = """
MATCH (t:Task)-[:DEPENDS_ON]->(dep:Task)
WHERE t.id IN $task_ids
RETURN t.id AS task_id, dep.id AS parent_id
"""

# Tool usage: every task that requires this tool, with its agent and parent goal.
TOOL_USAGE = """
MATCH (tool:Tool {id: $tool_id})<-[:REQUIRES]-(t:Task)
OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(a:Agent)
MATCH (g:Goal)-[:HAS_TASK]->(t)
RETURN t.id AS task_id,
       t.name AS task_name,
       a.name AS agent_name,
       g.id AS goal_id,
       g.name AS goal_name
ORDER BY g.name, t.name
"""

# The only mutation: simulate or clear an outage.
SET_TOOL_STATUS = """
MATCH (t:Tool {id: $tool_id})
SET t.status = $status
RETURN t.id AS id, t.name AS name, t.status AS status
"""
