from app.evals.evaluators.correctness import evaluate_correctness

def test_correctness_perfect_match():
    assert evaluate_correctness("hello world", "hello world") == 1.0

def test_correctness_no_overlap():
    assert evaluate_correctness("hello", "world") == 0.0