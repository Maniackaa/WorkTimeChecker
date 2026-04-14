import json

from config.max_settings import BASE_DIR


def read_max_workers_from_json() -> dict[str, str]:
    """
    Читает workers_max.json — тот же формат, что workers.json:
    [{"user_id": "<id в MAX>", "fio": "..."}, ...]

    Пустой или нечисловой user_id пропускается (заготовка под заполнение после /id в MAX).
    """
    file_path = BASE_DIR / "workers_max.json"
    users: dict[str, str] = {}
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return {}
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("user_id")
            fio = item.get("fio")
            if fio is None:
                continue
            uid = str(raw_id).strip() if raw_id is not None else ""
            if not uid.isdigit():
                continue
            users[uid] = str(fio).strip()
        return users
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}
