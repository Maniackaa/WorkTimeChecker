"""
Переменные окружения для бота MAX (добавьте в .env рядом с Telegram):

MAX_BOT_TOKEN=...
MAX_API_BASE_URL=https://platform-api.max.ru  # базовый URL API (maxapi + сырой REST в messaging)
MAX_DB_PATH=base_max.sqlite          # опционально, путь относительно корня проекта или абсолютный
MAX_GROUP_CHAT_ID=                   # опционально, chat_id группы для сводок и отпусков
MAX_ADMIN_IDS=123,456                # user_id людей (не id бота! /id у админа), через запятую
MAX_REPORT_INTERVAL_MINUTES=         # тест: например 5 — утро/вечер/end_task/отпуск подряд раз в N минут; пусто = боевой cron
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class MaxSettings(BaseSettings):
    MAX_BOT_TOKEN: str
    MAX_API_BASE_URL: str = "https://platform-api.max.ru"
    MAX_DB_PATH: Path | None = None
    MAX_GROUP_CHAT_ID: str | None = None
    # Через запятую user_id в MAX — кому отправить «Бот запущен» при старте (опционально)
    MAX_ADMIN_IDS: str | None = None
    # Тест: если > 0 — все рассылки подряд с этим интервалом (мин), без cron
    MAX_REPORT_INTERVAL_MINUTES: int | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MAX_REPORT_INTERVAL_MINUTES", mode="before")
    @classmethod
    def _empty_interval_none(cls, v):
        if v is None or v == "":
            return None
        return int(v)

    @property
    def api_base_url(self) -> str:
        return str(self.MAX_API_BASE_URL).strip().rstrip("/")

    @property
    def sqlite_path(self) -> Path:
        if self.MAX_DB_PATH is None:
            return BASE_DIR / "base_max.sqlite"
        p = Path(self.MAX_DB_PATH)
        return p if p.is_absolute() else (BASE_DIR / p)

    def get_admin_ids_for_notify(self) -> tuple[list[int], list[str]]:
        """Числовые user_id и фрагменты из .env, которые не удалось распознать (для логов)."""
        if not self.MAX_ADMIN_IDS:
            return [], []
        valid: list[int] = []
        invalid: list[str] = []
        for part in self.MAX_ADMIN_IDS.split(","):
            p = part.strip()
            if not p:
                continue
            if p.isdigit():
                valid.append(int(p))
            else:
                invalid.append(p)
        return valid, invalid

    @property
    def admin_id_list(self) -> list[int]:
        return self.get_admin_ids_for_notify()[0]


@lru_cache
def get_max_settings() -> MaxSettings:
    return MaxSettings()


max_settings = get_max_settings()
