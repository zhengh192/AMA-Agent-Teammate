from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ama_teammate.config import Settings
from ama_teammate.data_access.mysql import (
    MySQLCatalogError,
    MySQLCatalogSnapshot,
    MySQLConnectionOptions,
    MySQLReadOnlyConnector,
)


def _build_options(settings: Settings) -> MySQLConnectionOptions:
    errors = settings.super_agent_uat_validation_errors()
    if errors:
        raise ValueError("; ".join(errors))
    host = settings.ama_super_agent_uat_host
    username = settings.ama_super_agent_uat_username
    password = settings.ama_super_agent_uat_password
    if host is None or username is None or password is None:
        raise ValueError("UAT MySQL configuration is incomplete.")
    return MySQLConnectionOptions(
        host=host,
        port=settings.ama_super_agent_uat_port,
        username=username,
        password=password,
        database=settings.ama_super_agent_uat_database,
        allowed_tables=settings.super_agent_uat_allowed_table_names(),
        ssl_ca_path=settings.ama_super_agent_uat_ssl_ca_path,
        allow_insecure_transport=settings.ama_super_agent_uat_allow_insecure_transport,
        connect_timeout_seconds=settings.ama_super_agent_uat_connect_timeout_seconds,
        read_timeout_seconds=settings.ama_super_agent_uat_read_timeout_seconds,
        write_timeout_seconds=settings.ama_super_agent_uat_write_timeout_seconds,
        query_enabled=False,
    )


def render_markdown(snapshot: MySQLCatalogSnapshot) -> str:
    assessment = snapshot.privilege_assessment
    lines = [
        "# Super Agent UAT Catalog Snapshot",
        "",
        f"- Captured at: {snapshot.captured_at.isoformat()}",
        f"- Logical source: `{snapshot.source_id}`",
        f"- Database: `{snapshot.database}`",
        (
            f"- TLS: verified ({snapshot.tls_cipher})"
            if snapshot.tls_cipher
            else "- TLS: not enabled (explicit development exception)"
        ),
        f"- Read-only privileges: {'passed' if assessment.read_only else 'failed'}",
        f"- Privilege types: {', '.join(assessment.privileges) or 'none reported'}",
        f"- Missing allowlisted tables: {', '.join(snapshot.missing_allowlisted_tables) or 'none'}",
        "",
    ]
    lines.extend(f"- Scope warning: {warning}" for warning in assessment.scope_warnings)
    if assessment.scope_warnings:
        lines.append("")
    for table in snapshot.tables:
        indexed_columns: dict[str, list[str]] = {}
        for index in table.indexes:
            for column_name in index.columns:
                indexed_columns.setdefault(column_name, []).append(index.name)
        lines.extend(
            [
                f"## `{table.name}`",
                "",
                f"- Type: {table.table_type}",
                f"- Engine: {table.engine or 'Unknown'}",
                f"- Estimated rows: "
                f"{table.estimated_rows if table.estimated_rows is not None else 'Unknown'}",
                "",
                "| Column | Physical type | Nullable | Indexes | Comment |",
                "|---|---|---:|---|---|",
            ]
        )
        for column_snapshot in table.columns:
            comment = column_snapshot.comment.replace("|", "\\|")
            indexes = ", ".join(indexed_columns.get(column_snapshot.name, []))
            lines.append(
                f"| `{column_snapshot.name}` | `{column_snapshot.data_type}` | "
                f"{'yes' if column_snapshot.nullable else 'no'} | {indexes} | {comment} |"
            )
        lines.append("")
    return "\n".join(lines)


async def _catalog(options: MySQLConnectionOptions) -> MySQLCatalogSnapshot:
    connector, snapshot = await MySQLReadOnlyConnector.discover(options)
    await connector.close()
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ama-mysql-catalog",
        description="Read an allowlisted MySQL catalog without business rows.",
    )
    parser.add_argument("command", choices=["catalog"])
    parser.add_argument("--env-file", type=Path, default=Path(".env.uat"))
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    try:
        settings = Settings(_env_file=args.env_file)
        snapshot = asyncio.run(_catalog(_build_options(settings)))
    except (ValueError, MySQLCatalogError) as exc:
        message = exc.safe_message if isinstance(exc, MySQLCatalogError) else str(exc)
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(render_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
