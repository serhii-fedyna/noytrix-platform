# auth/schemas.py
from pydantic import BaseModel, EmailStr

class UserPublic(BaseModel):
    id: int
    email: EmailStr
    nick: str | None = None
    name: str | None = None
    avatar: str | None = None
    role: str
    plan: str
    provider: str | None = None
    email_verified: bool
    class Config:
        from_attributes = True

class RegisterStartReq(BaseModel):
    email: EmailStr
    password: str
    nick: str

class RegisterVerifyReq(BaseModel):
    email: EmailStr
    code: str

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class AuthBundle(BaseModel):
    user: UserPublic
    tokens: Tokens

class ResetStartReq(BaseModel):
    email: EmailStr

class ResetConfirmReq(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class GoogleAuthReq(BaseModel):
    access_token: str  # получаем из клиента, бэкенд сам спросит userinfo у Google
