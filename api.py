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


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt else ""


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

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)