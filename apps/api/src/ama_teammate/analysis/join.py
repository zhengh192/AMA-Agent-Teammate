from __future__ import annotations

import re

import duckdb
import pandas as pd

from ama_teammate.analysis.models import Dataset, JoinPlan, JoinQuality
from ama_teammate.analysis.quality import assess_dataset_quality
from ama_teammate.domain.models import new_id

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class JoinPolicyViolation(ValueError):
    pass


class BoundedDuckDBJoiner:
    def join(self, left: Dataset, right: Dataset, plan: JoinPlan) -> tuple[Dataset, JoinQuality]:
        self._validate(left, right, plan)
        left_frame = pd.DataFrame(left.rows)
        right_frame = pd.DataFrame(right.rows)
        left_frame[plan.left_key] = left_frame[plan.left_key].astype("string")
        right_frame[plan.right_key] = right_frame[plan.right_key].astype("string")
        duplicate_left = int(left_frame[plan.left_key].duplicated(keep=False).sum())
        duplicate_right = int(right_frame[plan.right_key].duplicated(keep=False).sum())

        left_keys = set(left_frame[plan.left_key].dropna().astype(str))
        right_keys = set(right_frame[plan.right_key].dropna().astype(str))
        matched_left = int(left_frame[plan.left_key].astype(str).isin(right_keys).sum())
        left_unmatched_rate = 0.0 if left.row_count == 0 else 1 - matched_left / len(left_frame)
        right_unmatched = len(right_keys - left_keys)
        right_unmatched_rate = 0.0 if not right_keys else right_unmatched / len(right_keys)

        connection = duckdb.connect(database=":memory:", config={"enable_external_access": "false"})
        try:
            connection.register("left_result", left_frame)
            connection.register("right_result", right_frame)
            query = (
                'SELECT l.*, r.* EXCLUDE ("' + plan.right_key + '") '
                "FROM left_result AS l "
                f"{plan.join_type.upper()} JOIN right_result AS r "
                f'ON l."{plan.left_key}" = r."{plan.right_key}" '
                f"LIMIT {plan.max_output_rows + 1}"
            )
            result_frame = connection.execute(query).fetchdf()
        finally:
            connection.close()
        if len(result_frame) > plan.max_output_rows:
            raise JoinPolicyViolation("Cross-source join exceeded the approved output row limit.")
        result_frame = result_frame.astype(object).where(pd.notna(result_frame), None)
        rows = [
            {str(key): value for key, value in row.items()}
            for row in result_frame.to_dict(orient="records")
        ]
        columns = [str(column) for column in result_frame.columns]
        warnings: list[str] = []
        weak = max(left_unmatched_rate, right_unmatched_rate) > 0.2
        if weak:
            warnings.append("Join quality is weak because unmatched rate exceeds 20%.")
        if duplicate_left or duplicate_right:
            warnings.append("Join keys contain duplicates; cardinality may amplify rows.")
        quality = JoinQuality(
            left_rows=left.row_count,
            right_rows=right.row_count,
            output_rows=len(rows),
            matched_left_rows=matched_left,
            left_unmatched_rate=round(left_unmatched_rate, 6),
            right_unmatched_rate=round(right_unmatched_rate, 6),
            duplicate_left_keys=duplicate_left,
            duplicate_right_keys=duplicate_right,
            type_coercion=plan.type_coercion,
            weak=weak,
            warnings=warnings,
        )
        joined_quality = assess_dataset_quality(rows, columns)
        joined_quality.warnings.extend(warnings)
        dataset = Dataset(
            id=new_id(),
            source_ids=left.source_ids + right.source_ids,
            query_proposal_ids=left.query_proposal_ids + right.query_proposal_ids,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            result_bytes=len(result_frame.to_json().encode("utf-8")),
            quality=joined_quality,
        )
        return dataset, quality

    @staticmethod
    def _validate(left: Dataset, right: Dataset, plan: JoinPlan) -> None:
        if plan.join_type not in {"inner", "left"}:
            raise JoinPolicyViolation("Only inner and left joins are allowed.")
        if not IDENTIFIER.fullmatch(plan.left_key) or not IDENTIFIER.fullmatch(plan.right_key):
            raise JoinPolicyViolation("Join keys are invalid.")
        if plan.left_key not in left.columns or plan.right_key not in right.columns:
            raise JoinPolicyViolation("Join key is missing from a bounded source result.")
        if left.row_count * max(1, right.row_count) > 1_000_000:
            raise JoinPolicyViolation(
                "Cross-source join estimate exceeds the safe cardinality cap."
            )
