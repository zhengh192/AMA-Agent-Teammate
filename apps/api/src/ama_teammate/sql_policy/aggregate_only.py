from __future__ import annotations

from sqlglot import exp


def aggregate_only_violations(
    statement: exp.Expression, aggregate_only_columns: set[str] | frozenset[str]
) -> set[str]:
    """Return protected columns used outside a SELECT aggregate expression."""
    protected = {name.casefold() for name in aggregate_only_columns}
    violations: set[str] = set()
    blocked_contexts = (exp.Where, exp.Group, exp.Having, exp.Join, exp.Order)
    for column in statement.find_all(exp.Column):
        name = column.name.casefold()
        if name not in protected:
            continue
        node = column.parent
        inside_aggregate = False
        blocked_context = False
        while node is not None and not isinstance(node, exp.Select):
            if isinstance(node, exp.AggFunc):
                inside_aggregate = True
            if isinstance(node, blocked_contexts):
                blocked_context = True
            node = node.parent
        if not inside_aggregate or blocked_context:
            violations.add(name)
    return violations
