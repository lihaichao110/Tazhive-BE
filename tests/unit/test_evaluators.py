from app.evals.evaluators.correctness import evaluate_correctness
from app.evals.evaluators.faithfulness import evaluate_faithfulness
from app.evals.evaluators.relevance import evaluate_relevance


def test_correctness_perfect_match():
    assert evaluate_correctness("hello world", "hello world") == 1.0


def test_correctness_no_overlap():
    assert evaluate_correctness("hello", "world") == 0.0


def test_relevance_perfect():
    assert evaluate_relevance("hello world", "hello world") == 1.0


def test_faithfulness_without_context():
    assert evaluate_faithfulness("any answer", "") == 1.0
