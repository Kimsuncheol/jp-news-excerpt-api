from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    title: str
    summary: str
    link: str
    published_at: datetime | None


class ArticleList(BaseModel):
    total: int
    items: list[ArticleOut]


class CollectOut(BaseModel):
    new_articles: dict[str, int]


class ErrorOut(BaseModel):
    detail: str
