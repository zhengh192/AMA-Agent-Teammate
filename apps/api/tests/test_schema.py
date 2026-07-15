from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from ama_teammate.config import Settings


def test_required_phase_one_tables_exist(client: TestClient, settings: Settings) -> None:
    assert client.get("/api/health").status_code == 200
    database_path = settings.ama_metadata_database_url.split("///", 1)[1]
    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "users",
        "chat_sessions",
        "messages",
        "agent_runs",
        "graph_checkpoint_refs",
        "tool_calls",
        "approvals",
        "audit_events",
        "artifacts",
        "analysis_plans",
        "query_proposals",
        "query_executions",
        "datasets",
        "join_executions",
        "evidence_records",
        "analysis_results",
    } <= table_names
