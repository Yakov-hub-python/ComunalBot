from storage import HEATING_COEFFICIENT


def calculate_receipt(
    readings: dict,
    prev_readings: dict,
    tariffs: dict
) -> dict:
    """
    Рассчитывает квитанцию.

    readings:      {"hvs": 453, "gvs": 254, "gas": 61, "electricity": 9822}
    prev_readings: {"hvs": 448, "gvs": 251, "gas": 59, "electricity": 9725}
    tariffs:       {"water": 41.56, "sewage": 37.7, "gas": 118.53,
                    "electricity": 5.36, "heating": 1890}
    """
    d_hvs = readings["hvs"] - prev_readings["hvs"]
    d_gvs = readings["gvs"] - prev_readings["gvs"]
    d_gas = readings["gas"] - prev_readings["gas"]
    d_ee  = readings["electricity"] - prev_readings["electricity"]

    water     = round((d_hvs + d_gvs) * tariffs["water"], 2)
    sewage    = round((d_hvs + d_gvs) * tariffs["sewage"], 2)
    gas       = round(d_gas * tariffs["gas"], 2)
    electricity = round(d_ee * tariffs["electricity"], 2)
    heating   = round(d_gvs * tariffs["heating"] * HEATING_COEFFICIENT, 2)

    total = round(water + sewage + gas + electricity + heating, 2)

    return {
        "water": water,
        "sewage": sewage,
        "gas": gas,
        "electricity": electricity,
        "heating": heating,
        "total": total,
        "consumption": {
            "hvs": d_hvs,
            "gvs": d_gvs,
            "gas": d_gas,
            "electricity": d_ee
        },
        "tariffs_used": tariffs.copy()
    }


def validate_readings(new: float, old: float) -> bool:
    """Проверка: новое показание > предыдущего."""
    return new > old
