import dataclasses
import datetime
import time
from typing import List

from sqlalchemy import create_engine, ForeignKey, String, DateTime, \
    Integer, select, delete, Text, Date
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database


# db_url = f"postgresql+psycopg2://{conf.db.db_user}:{conf.db.db_password}@{conf.db.db_host}:{conf.db.db_port}/{conf.db.database}"
from config.bot_settings import BASE_DIR, logger

db_path = BASE_DIR / 'base.sqlite'
db_url = f"sqlite:///{db_path}"
engine = create_engine(db_url, echo=False)
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    def set(self, key, value):
        _session = Session(expire_on_commit=False)
        with _session:
            if isinstance(value, str):
                value = value[:999]
            setattr(self, key, value)
            _session.add(self)
            _session.commit()
            logger.debug(f'Изменено значение {key} на {value}')
            return self


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement=True)
    tg_id: Mapped[str] = mapped_column(String(30), unique=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=True)
    register_date: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    fio: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[int] = mapped_column(Integer(), default=0)
    last_message: Mapped[int] = mapped_column(Integer(), nullable=True)
    works: Mapped[List['Work']] = relationship(back_populates='user',
                                                  cascade='save-update, merge, delete',
                                                  passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f'{self.id}. {self.username or "-"} {self.tg_id}'


class Work(Base):
    __tablename__ = 'works'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement=True)
    date = mapped_column(Date(), nullable=True)
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    user: Mapped['User'] = relationship(back_populates='works',  lazy='selectin')
    begin = mapped_column(DateTime(), nullable=True)
    end = mapped_column(DateTime(), nullable=True)
    last_reaction = mapped_column(DateTime(), nullable=True)


class Timer:

    def __init__(self, text):
        self.text = text
        super().__init__()

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        end = time.perf_counter()
        delta = end - self.start
        print(f'Время выполнения "{self.text}": {round(delta,2)} c.')


if not database_exists(db_url):
    create_database(db_url)
Base.metadata.create_all(engine)
