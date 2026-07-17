from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ama_teammate.storage.schema import Base


class LearnedMetricRow(Base):
    __tablename__ = "learned_metric_definitions"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "metric_key",
            "version",
            name="uq_learned_metric_owner_key_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    aliases_json: Mapped[str] = mapped_column(Text)
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(32), index=True)
    definition_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]