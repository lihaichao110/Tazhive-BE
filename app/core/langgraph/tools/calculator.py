from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """计算一个数学表达式。输入：表达式字符串，如 '2 + 3 * 4'。输出：计算结果。"""
    try:
        # 安全地计算（仅支持简单运算）
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Error: {e}"