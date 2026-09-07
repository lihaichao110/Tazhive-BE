def evaluate_relevance(predicted: str, question: str) -> float:
    """
    粗略评估回答与问题的相关性
    逻辑：统计回答命中问题关键词的比例，衡量回答是否回应提问

    Args:
        predicted: 模型生成的回答文本
        question: 用户原始问题

    Returns:
        float: 相关性得分 [0.0, 1.0]
               1.0：回答覆盖问题全部关键词；
               0.0：回答没有出现问题里任何关键词。
    """
    # 如果问题为空，无法评估相关性，返回0分
    if not question:
        return 0.0

    # 将问题转为小写，按空格分割为词汇集合
    q_terms = set(question.lower().split())
    # 将模型回答转为小写，按空格分割为词汇集合
    p_terms = set(predicted.lower().split())

    # 计算交集：回答和问题共同拥有的关键词数量
    overlap = len(q_terms & p_terms)

    # 相关性 = 命中问题关键词数量 / 问题总关键词数量
    # 防止问题词汇集合为空的边界情况
    return overlap / len(q_terms) if q_terms else 0.0
