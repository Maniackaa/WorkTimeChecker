from datetime import datetime, date
from typing import Optional, List

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from database.db import engine, Session, Work, User

app = FastAPI()

# Pydantic model для ответа
class WorkResponse(BaseModel):
    date: str
    start: str
    end: Optional[str]
    dinners_min: str
    usernameTG: Optional[str]
    user_id: int


class UserListItemTG(BaseModel):
    """Пользователь Telegram-бота (base.sqlite)."""

    id: int
    tg_id: str
    username: Optional[str] = None
    fio: Optional[str] = None
    is_active: int
    is_worked: int
    vacation_to: Optional[str] = None
    register_date: Optional[str] = None


class UserListItemMax(BaseModel):
    """Пользователь MAX-бота (base_max.sqlite)."""

    id: int
    max_user_id: str
    username: Optional[str] = None
    name: Optional[str] = None
    fio: Optional[str] = None
    is_active: int
    is_worked: int
    vacation_to: Optional[str] = None
    register_date: Optional[str] = None


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt else None


def format_date(dt: date) -> str:
  return dt.strftime("%d.%m.%Y") if dt else None


@app.get("/getdata", response_model=List[WorkResponse])
async def get_data(
    from_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date (YYYY-MM-DD)"),
):
    """
    Получает список всех смен пользователей в заданном периоде.
    """
    session = Session()

    try:
        stmt = (
           select(Work, User.username, User.id)
           .join(User, User.id == Work.user_id)
           .where(Work.date >= from_date, Work.date <= to_date)
        )
        works = session.execute(stmt).all()
        result = []
        for work, username, user_id in works:
            result.append(
                WorkResponse(
                    date=format_date(work.date),
                    start=format_datetime(work.begin),
                    end=format_datetime(work.end) if work.end else None,
                    dinners_min=str(work.total_dinner // 60),
                    usernameTG=username,
                    user_id=user_id
                )
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/getdata_max", response_model=List[WorkResponse])
async def get_data_max(
    from_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: date = Query(..., description="End date (YYYY-MM-DD)"),
):
    """
    Смены из БД бота MAX (base_max.sqlite), формат ответа как у /getdata.
    Поле usernameTG — username пользователя в MAX (для совместимости схемы).
    """
    from database.db_max import SessionMax, UserMax, WorkMax

    session = SessionMax()

    try:
        stmt = (
            select(WorkMax, UserMax.username, UserMax.id)
            .join(UserMax, UserMax.id == WorkMax.user_id)
            .where(WorkMax.date >= from_date, WorkMax.date <= to_date)
        )
        works = session.execute(stmt).all()
        result = []
        for work, username, user_id in works:
            result.append(
                WorkResponse(
                    date=format_date(work.date),
                    start=format_datetime(work.begin),
                    end=format_datetime(work.end) if work.end else None,
                    dinners_min=str(work.total_dinner // 60),
                    usernameTG=username,
                    user_id=user_id,
                )
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/users", response_model=List[UserListItemTG])
async def list_users_tg():
    """Список пользователей из БД Telegram-бота (заготовка под отчёты / интеграции)."""
    session = Session()
    try:
        stmt = select(User).order_by(User.id)
        rows = session.execute(stmt).scalars().all()
        out: List[UserListItemTG] = []
        for u in rows:
            out.append(
                UserListItemTG(
                    id=u.id,
                    tg_id=u.tg_id,
                    username=u.username,
                    fio=u.fio,
                    is_active=u.is_active or 0,
                    is_worked=u.is_worked or 0,
                    vacation_to=format_date(u.vacation_to) if u.vacation_to else None,
                    register_date=format_datetime(u.register_date) if u.register_date else None,
                )
            )
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/users_max", response_model=List[UserListItemMax])
async def list_users_max():
    """Список пользователей из БД MAX-бота (заготовка под отчёты / интеграции)."""
    from database.db_max import SessionMax, UserMax

    session = SessionMax()
    try:
        stmt = select(UserMax).order_by(UserMax.id)
        rows = session.execute(stmt).scalars().all()
        out: List[UserListItemMax] = []
        for u in rows:
            out.append(
                UserListItemMax(
                    id=u.id,
                    max_user_id=u.max_user_id,
                    username=u.username,
                    name=u.name,
                    fio=u.fio,
                    is_active=u.is_active or 0,
                    is_worked=u.is_worked or 0,
                    vacation_to=format_date(u.vacation_to) if u.vacation_to else None,
                    register_date=format_datetime(u.register_date) if u.register_date else None,
                )
            )
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)