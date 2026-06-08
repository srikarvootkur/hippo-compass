from app.main import GoogleHealthCoachReviewRequest, deterministic_google_health_coach_review


def test_google_health_coach_medical_question_uses_boundary_response() -> None:
    response = deterministic_google_health_coach_review(
        GoogleHealthCoachReviewRequest(
            question="Do I have a heart problem?",
            activity_summary={"record_count": 1, "total_active_minutes": 20, "active_days": 1},
            evidence_pack=[],
        )
    )

    assert response["safety_level"] == "medical_boundary"
    assert "cannot diagnose" in response["summary"]
    assert response["memory_candidates"] == []


def test_google_health_coach_consistency_question_returns_next_actions() -> None:
    response = deterministic_google_health_coach_review(
        GoogleHealthCoachReviewRequest(
            question="How should I improve workout consistency?",
            activity_summary={
                "record_count": 3,
                "total_active_minutes": 90,
                "guideline_scaled_target_active_minutes": 150,
                "active_days": 3,
                "exercise_type_counts": {"STRENGTH_TRAINING": 2, "WALKING": 1},
            },
            evidence_pack=[
                {
                    "title": "CDC Adult Activity Guidelines",
                    "url": "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html",
                    "summary": "Adults benefit from regular activity.",
                }
            ],
        )
    )

    assert response["safety_level"] == "wellness"
    assert response["next_actions"]
    assert response["citations"][0]["title"] == "CDC Adult Activity Guidelines"
