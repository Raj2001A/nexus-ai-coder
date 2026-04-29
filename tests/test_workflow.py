from backend.graph.workflow import should_retry_or_finish


def test_router_finishes_when_review_passes():
    state = {
        "review_passed": True,
        "iteration_count": 1,
        "max_iterations": 3,
    }

    assert should_retry_or_finish(state) == "finalize"


def test_router_finishes_when_max_iterations_reached():
    state = {
        "review_passed": False,
        "iteration_count": 3,
        "max_iterations": 3,
    }

    assert should_retry_or_finish(state) == "finalize"


def test_router_retries_when_review_fails_and_budget_remains():
    state = {
        "review_passed": False,
        "iteration_count": 1,
        "max_iterations": 3,
    }

    assert should_retry_or_finish(state) == "executor"
