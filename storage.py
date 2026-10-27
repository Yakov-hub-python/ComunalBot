import json
import os
from datetime import datetime

DATA_FILE = "data.json"

HEATING_COEFFICIENT = 0.0609

DEFAULT_DATA = {
    "tariffs": {
        "water": None,
        "sewage": None,
        "gas": None,
        "electricity": None,
        "heating": None
    },
    "meters": {
        "hvs": {},
        "gvs": {},
        "gas": {},
        "electricity": {}
    },
    "receipts": {}
}


def load_data() -> dict:
    """Загрузка данных из JSON-файла."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_DATA.copy()


def save_data(data: dict):
    """Сохранение данных в JSON-файл."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_current_month_key() -> str:
    """Возвращает ключ текущего месяца ММ.ГГГГ."""
    return datetime.now().strftime("%m.%Y")


def month_key_to_name(key: str) -> str:
    """Конвертирует ключ ММ.ГГГГ в название месяца."""
    months = {
        "01": "Январь", "02": "Февраль", "03": "Март",
        "04": "Апрель", "05": "Май", "06": "Июнь",
        "07": "Июль", "08": "Август", "09": "Сентябрь",
        "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь"
    }
    mm, yyyy = key.split(".")
    return f"{months.get(mm, mm)} {yyyy}"


def month_key_to_date(key: str) -> datetime:
    """Конвертирует ключ ММ.ГГГГ в datetime."""
    return datetime.strptime(key, "%m.%Y")


def get_previous_month_key(current_key: str) -> str | None:
    """Возвращает ключ предыдущего месяца."""
    dt = month_key_to_date(current_key)
    if dt.month == 1:
        prev = dt.replace(year=dt.year - 1, month=12)
    else:
        prev = dt.replace(month=dt.month - 1)
    return prev.strftime("%m.%Y")


def get_sorted_month_keys(receipts: dict) -> list[str]:
    """Возвращает отсортированные ключи месяцев."""
    return sorted(receipts.keys(), key=month_key_to_date)


def get_last_meter_reading(meter_name: str, data: dict) -> float | None:
    """Возвращает последнее показание счётчика."""
    meter_data = data["meters"].get(meter_name, {})
    if not meter_data:
        return None
    last_key = max(meter_data.keys(), key=month_key_to_date)
    return meter_data[last_key]


def get_last_meter_month(meter_name: str, data: dict) -> str | None:
    """Возвращает месяц последнего показания счётчика."""
    meter_data = data["meters"].get(meter_name, {})
    if not meter_data:
        return None
    return max(meter_data.keys(), key=month_key_to_date)


def get_meter_readings_for_month(meter_name: str, month_key: str, data: dict) -> float | None:
    """Возвращает показание счётчика за указанный месяц."""
    return data["meters"].get(meter_name, {}).get(month_key)


def add_meter_readings(month_key: str, readings: dict, data: dict) -> dict:
    """
    Добавляет показания счётчиков за месяц.
    readings = {"hvs": 453, "gvs": 254, "gas": 61, "electricity": 9822}
    """
    for meter_name, value in readings.items():
        if meter_name not in data["meters"]:
            data["meters"][meter_name] = {}
        data["meters"][meter_name][month_key] = value
    return data


def add_receipt(month_key: str, receipt: dict, data: dict) -> dict:
    """Сохраняет квитанцию за месяц."""
    data["receipts"][month_key] = receipt
    return data


def delete_receipt(month_key: str, data: dict) -> bool:
    """Удаляет квитанцию и связанные показания за месяц."""
    if month_key in data["receipts"]:
        del data["receipts"][month_key]
        for meter_name in data["meters"]:
            data["meters"][meter_name].pop(month_key, None)
        return True
    return False


def is_setup_complete(data: dict) -> bool:
    """Проверяет, завершена ли начальная настройка."""
    tariffs = data["tariffs"]
    return all(v is not None for v in tariffs.values())


def has_initial_readings(data: dict) -> bool:
    """Проверяет, введены ли начальные показания."""
    return any(len(v) > 0 for v in data["meters"].values())
