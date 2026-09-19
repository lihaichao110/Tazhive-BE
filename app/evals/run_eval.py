import asyncio
import json

from app.core.config import settings

# 导入LangGraph supervisor图实例
from app.core.langgraph.graph import get_supervisor_graph

# 导入三个评估指标函数：正确性、忠实度、相关性
from app.evals.evaluators.correctness import evaluate_correctness
from app.evals.evaluators.faithfulness import evaluate_faithfulness
from app.evals.evaluators.relevance import evaluate_relevance


async def run_evaluation(dataset_path: str):
    """
    运行Agent评测主函数
    :param dataset_path: 评测数据集jsonl文件路径，每行一条样本
    """
    # 读取jsonl数据集：逐行解析json，得到评测样本列表
    with open(dataset_path, encoding="utf-8") as f:
        samples = [json.loads(line) for line in f]

    # 初始化LangGraph supervisor图实例
    agent = await get_supervisor_graph()

    # 初始化分数存储字典，保存每个指标所有样本得分
    scores: dict[str, list[float]] = {"correctness": [], "faithfulness": [], "relevance": []}

    # 遍历每一条评测样本，逐个执行Agent推理 + 指标打分
    for sample in samples:
        question = sample["question"]  # 用户问题
        golden = sample.get("golden_answer", "")  # 标准答案（金标准）
        context = sample.get("context", "")  # 参考上下文（用于faithfulness评估）

        # 构造Agent输入状态
        from langchain_core.messages import HumanMessage

        input_state = {
            "messages": [HumanMessage(content=question)],  # 用户提问消息
            "model": settings.llm_default_model,
            "temperature": settings.llm_default_temperature,
            "system_prompt": "你是一个乐于助人的助手。",
        }

        # LangGraph配置：设置thread_id，区分不同评测会话，避免状态串扰
        config = {"configurable": {"thread_id": f"eval-{sample.get('id', '')}"}}

        # 异步调用Agent执行推理，获取完整输出状态
        result = await agent.ainvoke(input_state, config=config)

        # 取出Agent最后一条回复消息
        assistant_message = result["messages"][-1]
        # 提取模型预测回答文本，做兼容处理防止非标准消息对象
        predicted = (
            assistant_message.content
            if hasattr(assistant_message, "content")
            else str(assistant_message)
        )

        # 执行三项评估打分，将得分存入对应列表
        # correctness：预测回答与标准答案的匹配程度
        scores["correctness"].append(evaluate_correctness(predicted, golden))
        # faithfulness：回答是否忠实于给定上下文，不产生幻觉
        scores["faithfulness"].append(evaluate_faithfulness(predicted, context))
        # relevance：回答和用户提问是否相关
        scores["relevance"].append(evaluate_relevance(predicted, question))

    # 计算并打印每个指标的平均得分
    for metric, values in scores.items():
        avg = sum(values) / len(values) if values else 0.0
        print(f"{metric}: {avg:.4f}")


if __name__ == "__main__":
    import sys

    print(f"sys.argv:{sys.argv}")
    # 命令行传参：传入数据集路径；不传则使用默认数据集路径
    dataset = sys.argv[1] if len(sys.argv) > 1 else "app/evals/datasets/qa_golden.jsonl"
    # 启动异步主函数
    asyncio.run(run_evaluation(dataset))
