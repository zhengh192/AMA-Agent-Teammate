from __future__ import annotations

from ama_teammate.analysis.models import AnalysisComputation
from ama_teammate.domain.models import EpistemicLabel


class EvidenceValidationError(ValueError):
    pass


class EvidenceValidator:
    def validate(self, computation: AnalysisComputation) -> None:
        evidence_ids = {item.id for item in computation.evidence}
        allowed_labels = {label.value for label in EpistemicLabel}
        for conclusion in computation.conclusions:
            if not conclusion.evidence_ids or not set(conclusion.evidence_ids).issubset(
                evidence_ids
            ):
                raise EvidenceValidationError("Every material conclusion must link to evidence.")
            if conclusion.epistemic_label not in allowed_labels:
                raise EvidenceValidationError("Conclusion has an invalid epistemic label.")
            lower = conclusion.text.lower()
            causal_terms = ("caused", "causes", "because of", "drives")
            if (
                any(term in lower for term in causal_terms)
                and conclusion.epistemic_label != EpistemicLabel.CONFIRMED.value
            ):
                raise EvidenceValidationError("Unsupported causal language is blocked.")
