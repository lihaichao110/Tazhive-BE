def evaluate_correctness(predicted: str, golden: str) -> float:
    """
    基于关键词重叠的简单正确性评估，返回 0~1 之间的分数

    Args:
        predicted:模型预测出来的回答文本
        golden: 标准答案
    """
    if not golden:
        return 0.0
    pred_terms = set(predicted.lower().split())
    gold_terms = set(golden.lower().split())
    if not gold_terms:
        return 0.0
    overlap = len(pred_terms & gold_terms)
    return overlap / len(gold_terms)
