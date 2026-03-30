"""
database.py
===========
SQLite 設定（MVP 階段）。
正式版換 PostgreSQL 只需改 DATABASE_URL，其餘不動。
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "novel_analyzer.db"
)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def init_db():
    """建立所有資料表（若不存在）"""
    from backend.app.models import scene_framework_card  # noqa: 觸發模型註冊
    Base.metadata.create_all(bind=engine)
    print(f"DB 初始化完成：{DB_PATH}")
