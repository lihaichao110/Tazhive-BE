def evaluate_faithfulness(predicted: str, context: str = "") -> float:
    """
    基于回答中是否包含上下文中未出现的词来粗略评估忠实度
    忠实度：模型回答的内容是否全部来源于给定上下文，不凭空编造信息

    Args:
        predicted: 模型生成的回答文本
        context: 参考上下文（检索到的文档/参考资料）

    Returns:
        float: 忠实度得分，范围 [0.0, 1.0]
               1.0 代表回答所有词汇都来自上下文，完全忠实；
               0.0 代表回答所有词汇都不在上下文里，完全幻觉。
    """
    # 如果没有提供上下文，没有依据判断是否幻觉，直接返回满分1.0
    if not context:
        return 1.0

    # 把上下文转为小写，按空格切分，得到上下文词汇集合
    context_terms = set(context.lower().split())
    # 把模型预测回答转为小写，按空格切分，得到回答词汇集合
    pred_terms = set(predicted.lower().split())

    # 集合差集：找出【回答里有，但上下文里不存在】的词汇，即幻觉词汇
    unsupported = pred_terms - context_terms

    # 如果模型回答为空，返回0分
    if not pred_terms:
        return 0.0

    # 计算：1 - (幻觉词数量 / 回答总词数)
    # 幻觉词占比越高，得分越低；没有幻觉词则得1.0
    return 1.0 - len(unsupported) / len(pred_terms)
