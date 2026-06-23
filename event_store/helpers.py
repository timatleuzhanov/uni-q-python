from datetime import datetime, timezone


# Функция `get_timestamp` получает и возвращает вычисленные/запрошенные данные.
def get_timestamp() -> datetime:
    """
    Возвращает текущий UTC timestamp.
    Используется внутри Message для установки времени события.
    """
    return datetime.now(timezone.utc)
