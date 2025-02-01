import json

from config.bot_settings import BASE_DIR


def read_users_from_json() -> dict:
    """
    Читает пользователей из JSON файла.
    """
    file_path = BASE_DIR / "workers.json"
    users = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                users[item['user_id']] = item['fio']
        return users
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Invalid json in {file_path}")
        return {}
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}


if __name__ == "__main__":
    file_path = BASE_DIR / "workers.json"  # Замените на ваш путь к файлу
    users_data = read_users_from_json()
    if users_data:
        for user_id, fio in users_data.items():
            print(f"ID: {user_id}, ФИО: {fio}")
    else:
        print("No users loaded")
