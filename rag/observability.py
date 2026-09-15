import json
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = "data/observability.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ask_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    question TEXT NOT NULL,
    retrieved_chunks TEXT NOT NULL,
    sources TEXT,
    best_distance REAL,
    gate_fired INTEGER NOT NULL,
    answer TEXT,
    degraded INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL
)
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_TABLE_SQL)
    return conn


def log_ask(
    timestamp: str,
    question: str,
    retrieved_chunks: list,
    sources: list,
    best_distance: Optional[float],
    gate_fired: bool,
    answer: str,
    degraded: bool,
    latency_ms: int,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO ask_log
                (timestamp, question, retrieved_chunks, sources, best_distance, gate_fired, answer, degraded, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                question,
                json.dumps(retrieved_chunks),
                json.dumps(sources),
                best_distance,
                int(gate_fired),
                answer,
                int(degraded),
                latency_ms,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_ask_log(db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT timestamp, question, retrieved_chunks, sources, best_distance, "
            "gate_fired, answer, degraded, latency_ms FROM ask_log ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "timestamp": row[0],
            "question": row[1],
            "retrieved_chunks": json.loads(row[2]),
            "sources": json.loads(row[3]) if row[3] is not None else [],
            "best_distance": row[4],
            "gate_fired": bool(row[5]),
            "answer": row[6],
            "degraded": bool(row[7]),
            "latency_ms": row[8],
        }
    finally:
        conn.close()
