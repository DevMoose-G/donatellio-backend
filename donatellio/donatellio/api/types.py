from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

class RequestCreateImage(BaseModel):
    prompt: str
    n: int
    size: str
    quality: str

class RequestEditImage(BaseModel):
    project_id: str
    original_image_url: str
    prompt: str
    n: int
    size: str
    quality: str

class RequestCreateUser(BaseModel):
    username: str
    email: str
    password: str

class RequestLoginUser(BaseModel):
    password: str
    username: Optional[str] = None
    email: Optional[str] = None

class RequestGetElaboratingQuestions(BaseModel):
    project_id: str
    prompt: str
    image_id: Optional[str] = None


class ItemImagePromptChat(BaseModel):
    prompt: str
    created_at: datetime
    original_image_url: Optional[str] = None

class ResponseImagePromptChat(BaseModel):
    chats: List[ItemImagePromptChat]