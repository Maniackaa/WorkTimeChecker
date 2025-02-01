import dataclasses
import datetime
import time
from typing import List

from sqlalchemy import create_engine, ForeignKey, String, DateTime, \
    Integer, select, delete, Text, Date, inspect
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database


# db_url = f"postgresql+psycopg2://{conf.db.db_user}:{conf.db.db_password}@{conf.db.db_host}:{conf.db.db_port}/{conf.db.database}"
from config.bot_settings import BASE_DIR, logger
from services.func import read_users_from_json

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
    is_worked: Mapped[int] = mapped_column(Integer(), default=0)
    vacation_to: Mapped[datetime.datetime] = mapped_column(Date(), nullable=True)
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
    begin: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    end: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    last_reaction: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    dinner_start: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    dinner_end: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    total_dinner: Mapped[int] = mapped_column(Integer(), default=0)


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

# Добавление юзеров
def add_users_if_not_exists(session, users_data):
    """
    Добавляет пользователей в базу данных, если они еще не существуют.

    Args:
        session: Сессия SQLAlchemy.
        users_Список словарей с данными пользователей.
            Каждый словарь должен содержать ключи 'tg_id' и 'fio'.
    """
    print(users_data)
    inspector = inspect(session.get_bind())
    if not inspector.has_table('users'):
        Base.metadata.create_all(session.get_bind())

    for tg_id, fio in users_data.items():
        # Проверяем, существует ли пользователь
        stmt = select(User).where(User.tg_id == tg_id)
        existing_user = session.scalars(stmt).first()

        if existing_user is None:
            new_user = User(
                tg_id=tg_id,
                fio=fio,
                is_active=1,
                is_worked=1,
                register_date=datetime.datetime.now()  # Устанавливаем текущую дату регистрации
            )
            session.add(new_user)
            session.commit()
            print(f"Added user: {tg_id} - {fio}")
        else:
            print(f"User already exists: {tg_id} - {fio}")


add_users_if_not_exists(Session(expire_on_commit=False), read_users_from_json())
