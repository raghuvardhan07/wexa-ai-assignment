"""Neo4j driver lifecycle and execution helpers."""
from contextlib import contextmanager
from time import sleep
from typing import Any, Iterator

from neo4j import Driver, GraphDatabase, Session
from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError

from cascade.config import get_settings

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = GraphDatabase.driver(
            s.cognodb_uri,
            auth=(s.cognodb_username, s.cognodb_password),
            connection_timeout=10,
            max_connection_lifetime=300,
        )
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def ping() -> bool:
    try:
        get_driver().verify_connectivity()
        return True
    except Exception:
        return False


@contextmanager
def db_session() -> Iterator[Session]:
    s = get_settings()
    sess = get_driver().session(database=s.cognodb_database)
    try:
        yield sess
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------


def _run(session: Session, cypher: str, **params: Any) -> list[dict]:
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            return [r.data() for r in session.run(cypher, **params)]
        except (ServiceUnavailable, SessionExpired, TransientError) as e:
            last_err = e
            if attempt < 2:
                sleep(0.2 * (attempt + 1))
    raise last_err


def _one(session: Session, cypher: str, **params: Any) -> int:
    rows = _run(session, cypher, **params)
    return int(rows[0]["n"]) if rows else 0
