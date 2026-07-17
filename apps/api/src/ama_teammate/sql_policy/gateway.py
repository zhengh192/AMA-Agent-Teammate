from __future__ import annotations

from collections.abc import Iterable

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from ama_teammate.data_access.models import DataSourceConfig
from ama_teammate.sql_policy.models import QueryProposal, SQLPolicyViolation, ValidatedQuery

POLICY_VERSION = "sql-readonly-v1"


class SQLSafetyGateway:
    def validate(self, proposal: QueryProposal, source: DataSourceConfig) -> ValidatedQuery:
        if not source.read_only:
            raise SQLPolicyViolation(
                "source_not_read_only", "The selected source is not read-only."
            )
        if proposal.source_id != source.id:
            raise SQLPolicyViolation(
                "source_mismatch", "Query source does not match policy source."
            )
        if self._has_comments(proposal.sql):
            raise SQLPolicyViolation("comments_not_allowed", "SQL comments are not allowed.")
        try:
            statements = parse(proposal.sql, read=source.dialect.value)
        except ParseError as exc:
            raise SQLPolicyViolation("parse_error", "SQL could not be parsed safely.") from exc
        if len(statements) != 1:
            raise SQLPolicyViolation("multiple_statements", "Exactly one SQL statement is allowed.")
        statement = statements[0]
        if not isinstance(statement, exp.Select):
            raise SQLPolicyViolation("read_only_required", "Only SELECT queries are allowed.")
        if self._contains_write_or_admin(statement):
            raise SQLPolicyViolation("write_or_admin", "Write and administrative SQL are blocked.")
        if any(True for _ in statement.find_all(exp.Star)):
            raise SQLPolicyViolation(
                "wildcard_not_allowed",
                "Wildcard columns are blocked; select approved columns explicitly.",
            )

        table_names, schemas = self._tables(statement)
        allowed_tables = {name.lower() for name in source.tables}
        if not table_names or not table_names.issubset(allowed_tables):
            raise SQLPolicyViolation("table_not_allowed", "SQL references an unapproved table.")
        allowed_schemas = {schema.lower() for schema in source.allowed_schemas}
        if schemas and not schemas.issubset(allowed_schemas):
            raise SQLPolicyViolation("schema_not_allowed", "SQL references an unapproved schema.")

        allowed_function_types = (
            exp.Sum,
            exp.Count,
            exp.Avg,
            exp.Min,
            exp.Max,
            exp.Coalesce,
            exp.Cast,
            exp.Case,
            exp.If,
            exp.And,
            exp.Or,
        )
        if any(
            not isinstance(function, allowed_function_types)
            for function in statement.find_all(exp.Func)
        ):
            raise SQLPolicyViolation(
                "function_not_allowed", "SQL references a function outside the read-only allowlist."
            )

        column_names = {column.name.lower() for column in statement.find_all(exp.Column)}
        denied = {name.lower() for name in source.denied_columns}
        if column_names & denied:
            raise SQLPolicyViolation("column_denied", "SQL references a denied column.")
        available_columns = set().union(
            *(source.tables[name].column_names for name in table_names if name in source.tables)
        )
        unknown = {name for name in column_names if name not in available_columns}
        aliases = {alias.lower() for alias in self._select_aliases(statement)}
        if unknown - aliases:
            raise SQLPolicyViolation("column_not_allowed", "SQL references an unapproved column.")

        parameter_names = {placeholder.name for placeholder in statement.find_all(exp.Placeholder)}
        supplied_names = set(proposal.parameters)
        if parameter_names != supplied_names:
            raise SQLPolicyViolation(
                "parameter_mismatch",
                "SQL parameters must exactly match the approved parameter set.",
            )
        if proposal.max_rows > source.max_rows:
            raise SQLPolicyViolation("row_limit", "Requested row limit exceeds source policy.")
        if proposal.max_result_bytes > source.max_result_bytes:
            raise SQLPolicyViolation("byte_limit", "Requested result size exceeds source policy.")
        if proposal.timeout_seconds > source.timeout_seconds:
            raise SQLPolicyViolation("timeout_limit", "Requested timeout exceeds source policy.")

        limit = statement.args.get("limit")
        if limit is not None:
            limit_value = self._literal_int(limit.expression)
            if limit_value is None or limit_value > proposal.max_rows:
                raise SQLPolicyViolation("row_limit", "SQL LIMIT exceeds the approved row limit.")
        else:
            statement = statement.limit(proposal.max_rows)

        return ValidatedQuery(
            proposal_id=proposal.id,
            source_id=source.id,
            dialect=source.dialect.value,
            normalized_sql=statement.sql(dialect=source.dialect.value, pretty=False),
            executable_sql=statement.sql(dialect=source.execution_dialect, pretty=False),
            parameters=proposal.parameters,
            referenced_tables=sorted(table_names),
            referenced_columns=sorted(column_names),
            max_rows=proposal.max_rows,
            max_result_bytes=proposal.max_result_bytes,
            timeout_seconds=proposal.timeout_seconds,
            policy_version=POLICY_VERSION,
        )

    @staticmethod
    def _has_comments(sql: str) -> bool:
        return "--" in sql or "/*" in sql or "*/" in sql

    @staticmethod
    def _contains_write_or_admin(statement: exp.Expression) -> bool:
        blocked: tuple[type[exp.Expression], ...] = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Create,
            exp.Drop,
            exp.Alter,
            exp.Merge,
            exp.Command,
            exp.Transaction,
            exp.Into,
        )
        return any(isinstance(node, blocked) for node in statement.walk())

    @staticmethod
    def _tables(statement: exp.Expression) -> tuple[set[str], set[str]]:
        tables: set[str] = set()
        schemas: set[str] = set()
        cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
        for table in statement.find_all(exp.Table):
            name = table.name.lower()
            if name in cte_names:
                continue
            tables.add(name)
            if table.db:
                schemas.add(table.db.lower())
        return tables, schemas

    @staticmethod
    def _select_aliases(statement: exp.Select) -> Iterable[str]:
        for expression in statement.expressions:
            if expression.alias:
                yield expression.alias

    @staticmethod
    def _literal_int(expression: exp.Expression | None) -> int | None:
        if isinstance(expression, exp.Literal) and not expression.is_string:
            try:
                return int(expression.this)
            except (TypeError, ValueError):
                return None
        return None
