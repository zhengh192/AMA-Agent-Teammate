from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ama_teammate.storage.schema import Base


class AnalysisPlanRow(Base):
    __tablename__ = "analysis_plans"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), unique=True, index=True)
    question_hash: Mapped[str] = mapped_column(String(128))
    goal: Mapped[str] = mapped_column(Text)
    analysis_type: Mapped[str] = mapped_column(String(64))
    chart_type: Mapped[str] = mapped_column(String(64))
    plan_json: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class QueryProposalRow(Base):
    __tablename__ = "query_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("analysis_plans.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(120), index=True)
    dialect: Mapped[str] = mapped_column(String(32))
    normalized_sql: Mapped[str] = mapped_column(Text)
    executable_sql: Mapped[str] = mapped_column(Text)
    parameters_json: Mapped[str] = mapped_column(Text)
    sql_hash: Mapped[str] = mapped_column(String(128))
    max_rows: Mapped[int]
    max_result_bytes: Mapped[int]
    timeout_seconds: Mapped[float]
    policy_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime]


class QueryExecutionRow(Base):
    __tablename__ = "query_executions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("query_proposals.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(120))
    actual_sql: Mapped[str] = mapped_column(Text)
    sql_hash: Mapped[str] = mapped_column(String(128))
    parameters_json: Mapped[str] = mapped_column(Text)
    rows_returned: Mapped[int] = mapped_column(default=0)
    result_bytes: Mapped[int] = mapped_column(default=0)
    duration_ms: Mapped[float] = mapped_column(default=0)
    repair_attempt: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime]


class DatasetRow(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    source_ids_json: Mapped[str] = mapped_column(Text)
    query_proposal_ids_json: Mapped[str] = mapped_column(Text)
    columns_json: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int]
    result_bytes: Mapped[int]
    quality_json: Mapped[str] = mapped_column(Text)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    created_at: Mapped[datetime]


class JoinExecutionRow(Base):
    __tablename__ = "join_executions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("analysis_plans.id"))
    left_dataset_id: Mapped[str] = mapped_column(String(64))
    right_dataset_id: Mapped[str] = mapped_column(String(64))
    output_dataset_id: Mapped[str] = mapped_column(String(64))
    join_plan_json: Mapped[str] = mapped_column(Text)
    quality_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]


class EvidenceRow(Base):
    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    dataset_ids_json: Mapped[str] = mapped_column(Text)
    query_proposal_ids_json: Mapped[str] = mapped_column(Text)
    calculation: Mapped[str] = mapped_column(Text)
    support_json: Mapped[str] = mapped_column(Text)
    epistemic_label: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float]
    limitations_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]


class AnalysisResultRow(Base):
    __tablename__ = "analysis_results"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), unique=True, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("analysis_plans.id"))
    result_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    csv_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime]
