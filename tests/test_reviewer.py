from backend.agents import reviewer


def test_run_reviewer_parses_pass(monkeypatch):
    class FakeCrew:
        def __init__(self, *args, **kwargs):
            pass

        def kickoff(self):
            return "VERDICT: PASS\nAll checks passed."

    monkeypatch.setattr(reviewer, "Crew", FakeCrew)
    monkeypatch.setattr(reviewer, "create_reviewer_agent", lambda: object())
    monkeypatch.setattr(reviewer, "create_review_task", lambda *args, **kwargs: object())

    result = reviewer.run_reviewer("task", "plan", "execution")

    assert result["passed"] is True
    assert "VERDICT: PASS" in result["feedback"]
    assert result["issues"] == ""


def test_run_reviewer_parses_fail(monkeypatch):
    class FakeCrew:
        def __init__(self, *args, **kwargs):
            pass

        def kickoff(self):
            return "VERDICT: FAIL\n1. Missing tests."

    monkeypatch.setattr(reviewer, "Crew", FakeCrew)
    monkeypatch.setattr(reviewer, "create_reviewer_agent", lambda: object())
    monkeypatch.setattr(reviewer, "create_review_task", lambda *args, **kwargs: object())

    result = reviewer.run_reviewer("task", "plan", "execution")

    assert result["passed"] is False
    assert "VERDICT: FAIL" in result["feedback"]
    assert "Missing tests" in result["issues"]
