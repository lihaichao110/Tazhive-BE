from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    """
    用户注册请求体模型
    接收前端提交的注册表单参数，做数据校验
    """
    username: str
    """用户名"""
    email: EmailStr
    """邮箱地址，自动校验邮箱格式合法性"""
    password: str
    """用户明文密码，接口层接收后内部做哈希加密存储，不直接入库"""


class UserLogin(BaseModel):
    """
    用户登录请求体模型
    接收用户名密码用于身份校验
    """
    username: str
    """登录用户名"""
    password: str
    """登录明文密码，后端比对哈希校验"""


class TokenResponse(BaseModel):
    """
    JWT登录成功返回token响应模型
    OAuth2 标准返回格式
    """
    access_token: str
    """JWT访问令牌"""
    token_type: str = "bearer"
    """令牌类型，固定为 bearer"""
