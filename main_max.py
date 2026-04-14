"""
Точка входа бота MAX (учёт времени, отдельная БД base_max.sqlite).

Запуск: python main_max.py
.env: MAX_BOT_TOKEN, …; тест рассылок: MAX_REPORT_INTERVAL_MINUTES=5
"""
import asyncio
import logging

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from maxapi import Bot, Dispatcher

from config.max_settings import max_settings
from database import db_max  # noqa: F401
from max_app import context
from max_app.messaging import mid_from_response, send_message
from max_app.worktime_handlers import register_worktime_handlers
from services.db_func_max import (
    end_task_max,
    evening_send_max,
    morning_send_max,
    run_all_max_scheduled_reports,
    vocation_task_max,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("max_bot")

bot = Bot(max_settings.MAX_BOT_TOKEN)
bot.set_api_url(max_settings.api_base_url)
dp = Dispatcher()


@dp.on_started()
async def on_max_ready():
    """
    Локальный запуск polling (не путать с bot_started из API — то приходит как апдейт).
    Вызывается из Dispatcher.__ready после check_me().
    """
    log.info("MAX-бот готов (on_started); БД: %s", max_settings.sqlite_path)

    try:
        me = await bot.get_me()
        bot_uid = me.user_id
        log.info("MAX get_me: user_id бота=%s (@%s) — это НЕ тот id, что нужен в MAX_ADMIN_IDS", bot_uid, me.username)
    except Exception as e:
        log.warning("Не удалось get_me для проверки id бота: %s", e)
        bot_uid = None

    raw = max_settings.MAX_ADMIN_IDS
    admin_ids, invalid_parts = max_settings.get_admin_ids_for_notify()
    log.info(
        "Стартовое уведомление админам: MAX_ADMIN_IDS из .env=%r -> user_id=%s",
        raw,
        admin_ids,
    )
    if invalid_parts:
        log.warning(
            "MAX_ADMIN_IDS: пропущены нечисловые фрагменты (проверьте .env): %s",
            invalid_parts,
        )
    if raw and not admin_ids:
        log.warning(
            "MAX_ADMIN_IDS задан (%r), но ни одного числового user_id не распознано. "
            "Нужен формат: MAX_ADMIN_IDS=123456789 без кавычек, id через запятую.",
            raw,
        )
    if not admin_ids:
        log.info("Стартовое уведомление не отправляется: список админов пуст (задайте MAX_ADMIN_IDS).")
        return

    s = context.http_session
    if not s:
        log.error(
            "Стартовое уведомление не отправлено: context.http_session ещё None "
            "(ошибка порядка инициализации в main_max.py)."
        )
        return

    text = "Бот MAX (учёт времени) запущен"
    for aid in admin_ids:
        if bot_uid is not None and aid == bot_uid:
            log.error(
                "Старт: MAX_ADMIN_IDS содержит user_id=%s — это id самого бота (см. лог get_me). "
                "Укажите user_id человека-администратора (команда /id в MAX у этого человека).",
                aid,
            )
            continue
        log.info("Старт: отправка уведомления админу MAX user_id=%s", aid)
        try:
            result = await send_message(s, user_id=aid, text=text)
        except Exception as e:
            log.exception("Старт: исключение при отправке админу user_id=%s: %s", aid, e)
            continue
        if result is None:
            log.error(
                "Старт: админ user_id=%s не получил сообщение — API вернул ошибку или пустой ответ "
                "(см. выше лог max_app.messaging: HTTP и тело ответа). "
                "Часто нужно, чтобы этот пользователь хотя бы раз написал боту /start в личке.",
                aid,
            )
        else:
            mid = mid_from_response(result)
            log.info("Старт: уведомление админу user_id=%s отправлено, message mid=%s", aid, mid)


def _set_scheduled_jobs(scheduler: AsyncIOScheduler, session: aiohttp.ClientSession) -> None:
    interval = max_settings.MAX_REPORT_INTERVAL_MINUTES
    if interval is not None and interval > 0:
        log.warning(
            "MAX тестовый режим рассылок: все задачи (утро/вечер/end_task/отпуск) раз в %s мин.",
            interval,
        )
        scheduler.add_job(
            run_all_max_scheduled_reports,
            IntervalTrigger(minutes=interval),
            args=(session, scheduler),
            id="max_reports_interval",
            replace_existing=True,
        )
        return

    scheduler.add_job(morning_send_max, CronTrigger(hour=7, minute=59), args=(session,))
    scheduler.add_job(morning_send_max, CronTrigger(hour=8, minute=15), args=(session,))
    scheduler.add_job(morning_send_max, CronTrigger(hour=8, minute=30), args=(session,))
    scheduler.add_job(morning_send_max, CronTrigger(hour=8, minute=45), args=(session,))
    scheduler.add_job(morning_send_max, CronTrigger(hour=9, minute=0), args=(session,))

    scheduler.add_job(evening_send_max, CronTrigger(hour=17, minute=0), args=(session,))
    scheduler.add_job(end_task_max, CronTrigger(hour=18, minute=1, second=0), args=(session, scheduler))
    scheduler.add_job(vocation_task_max, CronTrigger(hour=18, minute=0, second=0), args=(session,))


async def main():
    register_worktime_handlers(dp)
    context.http_session = aiohttp.ClientSession()
    session = context.http_session

    _ids, _bad = max_settings.get_admin_ids_for_notify()
    log.info(
        "После загрузки .env: MAX_ADMIN_IDS=%r распознано id=%s отброшено=%s",
        max_settings.MAX_ADMIN_IDS,
        _ids,
        _bad if _bad else "—",
    )

    scheduler = AsyncIOScheduler()
    context.scheduler = scheduler
    _set_scheduled_jobs(scheduler, session)
    scheduler.start()
    log.info(
        "Старт polling MAX, sqlite=%s, API=%s",
        max_settings.sqlite_path,
        max_settings.api_base_url,
    )

    if max_settings.MAX_REPORT_INTERVAL_MINUTES and max_settings.MAX_REPORT_INTERVAL_MINUTES > 0:
        log.info("MAX: первый тестовый тик рассылок сразу (далее каждые %s мин.)", max_settings.MAX_REPORT_INTERVAL_MINUTES)
        await run_all_max_scheduled_reports(session, scheduler)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await session.close()
        context.http_session = None


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Остановлено пользователем")
