from __future__ import annotations

from ama_teammate.services.phase2_chat import PhaseTwoChatService


def test_safe_analysis_summary_withholds_database_text_samples() -> None:
    original = {
        "response_evidence": {
            "selected_path": {"agent_stage": "ka"},
            "incident_sample_count": 1,
            "samples": {
                "incident": [{"bot_response": "private database text"}],
                "baseline": [],
            },
        }
    }

    safe = PhaseTwoChatService._safe_analysis_summary(original)

    assert "samples" not in safe["response_evidence"]
    assert safe["response_evidence"]["samples_withheld_from_model"] is True
    assert "samples" in original["response_evidence"]