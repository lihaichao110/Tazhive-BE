# 导入prometheus_client监控库相关组件
# Counter：计数器，只增不减，用于统计事件发生次数
# Histogram：直方图，用于统计耗时、大小的分布情况
# generate_latest：将所有已注册指标转为Prometheus文本格式
# CONTENT_TYPE_LATEST：Prometheus指标响应的MIME类型
# FastAPI 请求对象，用于获取请求方法、路径等信息
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Starlette自定义响应，用于返回metrics接口数据
from starlette.responses import Response

# ====================== 定义监控指标 ======================
# 接口请求总计数器
# 指标名：app_requests_total
# 描述：接口总请求数量
# 标签labels：method请求方法、endpoint接口路径、status响应状态码
REQUEST_COUNT = Counter("app_requests_total", "请求总次数", ["method", "endpoint", "status"])

# 接口请求耗时直方图
# 指标名：app_request_duration_seconds
# 描述：接口请求耗时，单位秒
# 标签labels：method请求方法、endpoint接口路径
# Histogram会自动生成 _count(次数)、_sum(总耗时)、bucket分桶数据
REQUEST_DURATION = Histogram(
    "app_request_duration_seconds", "请求耗时（秒）", ["method", "endpoint"]
)

# LLM大模型调用次数计数器
# 指标名：app_llm_calls_total
# 描述：LLM模型调用总次数
# 标签labels：model 模型名称
LLM_CALL_COUNT = Counter("app_llm_calls_total", "LLM 调用次数", ["model"])

# LLM Token消耗计数器
# 指标名：app_llm_tokens_total
# 描述：LLM消耗token总数
# 标签labels：model模型名称，type类型(input输入token / output输出token)
LLM_TOKEN_USED = Counter(
    "app_llm_tokens_total",
    "已用 Token 数",
    ["model", "type"],  # 标签值：input/output
)


def metrics_endpoint():
    """
    Prometheus指标暴露接口
    对外返回所有监控指标的文本数据，供Prometheus服务拉取
    """
    # generate_latest() 获取全部指标数据，返回Response响应
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
