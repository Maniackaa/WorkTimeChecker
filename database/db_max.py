"""
Отдельная SQLite-база для бота MAX (не использует Telegram base.sqlite).
"""
import datetime
import logging
import time
from typing import List

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy_utils import create_database, database_exists

from config.max_settings import max_settings
from services.func_max import read_max_workers_from_json

log = logging.getLogger(__name__)

db_path = max_settings.sqlite_path
db_url = f"sqlite:///{db_path}"
engine = create_engine(db_url, echo=False)
SessionMax = sessionmaker(bind=engine)


class BaseMax(DeclarativeBase):
    def set(self, key, value):
        _session = SessionMax(expire_on_commit=False)
        with _session:
            if isinstance(value, str):
                value = value[:999]
            setattr(self, key, value)
            _session.add(self)
            _session.commit()
            log.debug("Изменено значение %s", key)
            return self


class UserMax(BaseMax):
    __tablename__ = "users_max"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    max_user_id: Mapped[str] = mapped_column(String(30), unique=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=True)
    register_date: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    fio: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[int] = mapped_column(Integer(), default=0)
    is_worked: Mapped[int] = mapped_column(Integer(), default=1)
    vacation_to: Mapped[datetime.date] = mapped_column(Date(), nullable=True)
    last_message: Mapped[str] = mapped_column(String(128), nullable=True)
    works: Mapped[List["WorkMax"]] = relationship(
        back_populates="user",
        cascade="save-update, merge, delete",
        passive_deletes=True,
        lazy="selectin",
        order_by="WorkMax.date, WorkMax.id",
    )

    def __repr__(self):
        return f"{self.id}. {self.username or '-'} {self.max_user_id}"


class Timer:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        end = time.perf_counter()
        log.debug('Время "%s": %.2f с', self.text, round(end - self.start, 2))


class WorkMax(BaseMax):
    __tablename__ = "works_max"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(Date(), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users_max.id", ondelete="CASCADE"))
    user: Mapped["UserMax"] = relationship(back_populates="works", lazy="selectin")
    begin: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    end: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    last_reaction: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    evening_prompt_at: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    dinner_start: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    dinner_end: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    total_dinner: Mapped[int] = mapped_column(Integer(), default=0)


if not database_exists(db_url):
    create_database(db_url)
BaseMax.metadata.create_all(engine)


def _migrate_works_max_evening_prompt() -> None:
    insp = inspect(engine)
    if not insp.has_table("works_max"):
        return
    cols = {c["name"] for c in insp.get_columns("works_max")}
    if "evening_prompt_at" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE works_max ADD COLUMN evening_prompt_at DATETIME"))
    log.info("БД MAX: добавлено поле works_max.evening_prompt_at")


_migrate_works_max_evening_prompt()


def _migrate_users_max_is_worked() -> None:
    """Как у Telegram User.is_worked=1 по умолчанию — иначе утренняя рассылка пустая."""
    insp = inspect(engine)
    if not insp.has_table("users_max"):
        return
    with engine.begin() as conn:
        conn.execute(text("UPDATE users_max SET is_worked = 1 WHERE is_worked = 0"))
    log.info("БД MAX: users_max.is_worked=0 приведено к 1 (паритет с TG)")


_migrate_users_max_is_worked()


def add_users_max_if_not_exists(session_factory, users_data: dict[str, str]) -> None:
    if not users_data:
        return
    session = session_factory(expire_on_commit=False)
    with session:
        inspector = inspect(session.get_bind())
        if not inspector.has_table("users_max"):
            BaseMax.metadata.create_all(session.get_bind())

        for max_uid, fio in users_data.items():
            stmt = select(UserMax).where(UserMax.max_user_id == str(max_uid))
            existing = session.scalars(stmt).first()
            if existing is None:
                session.add(
                    UserMax(
                        max_user_id=str(max_uid),
                        fio=fio,
                        is_active=1,
                        is_worked=1,
                        register_date=datetime.datetime.now(),
                    )
                )
                session.commit()
                log.info("MAX: добавлен пользователь %s — %s", max_uid, fio)


add_users_max_if_not_exists(SessionMax, read_max_workers_from_json())
