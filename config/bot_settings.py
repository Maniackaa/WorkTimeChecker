import logging
from functools import lru_cache
from pathlib import Path

import pytz as pytz
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog.typing import WrappedLogger, EventDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    BOT_TOKEN: str  # Токен для доступа к телеграм-боту
    ADMIN_IDS: list  # Список id администраторов бота
    BASE_DIR: Path = BASE_DIR
    TIMEZONE: str = "Europe/Moscow"
    USE_REDIS: bool = False
    LOG_TO_FILE: bool = False
    GROUP_ID: str
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env")

    @property
    def tz(self):
        return pytz.timezone(self.TIMEZONE)


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()


LOG_TO_FILE = settings.LOG_TO_FILE


def get_factory():
    log_file_dir = BASE_DIR / 'logs' / 'bot'
    print(f'LOG_TO_FILE: {LOG_TO_FILE}')
    if not LOG_TO_FILE:
        return structlog.PrintLoggerFactory()
    return structlog.WriteLoggerFactory(file=log_file_dir.with_suffix(".log").open("wt"))


def get_my_loggers():
    class LogJump:
        def __init__(
            self,
            full_path: bool = False,
        ) -> None:
            self.full_path = full_path

        def __call__(
            self, logger: WrappedLogger, name: str, event_dict: EventDict
        ) -> EventDict:
            if self.full_path:
                file_part = "\n" + event_dict.pop("pathname")
            else:
                file_part = event_dict.pop("filename")
            event_dict["location"] = f'"{file_part}:{event_dict.pop("lineno")}"'

            return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.CallsiteParameterAdder(
                [
                    # add either pathname or filename and then set full_path to True or False in LogJump below
                    # structlog.processors.CallsiteParameter.PATHNAME,
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ],
            ),
            LogJump(full_path=False),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        context_class=dict,
        # logger_factory=structlog.PrintLoggerFactory(),
        logger_factory=get_factory(),
        cache_logger_on_first_use=False,
    )
    return structlog.stdlib.get_logger()


logger = get_my_loggers()
logger.info(str(settings))
