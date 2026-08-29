from fastapi import APIRouter
from app.api.v1 import health, auth

# 创建顶层v1版本路由实例，作为v1下所有接口的总路由容器
api_router = APIRouter()

# 将health模块内部的子路由注册到总路由api_router上
# tags=["health"]：给这一组接口打上标签，会在Swagger接口文档中分组展示
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
