"""Утилиты для расчёта периодов статистики (всё в MSK, сброс в 02:00)."""

from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))
RESET_HOUR = 2  # сброс в 02:00 MSK


def now_msk() -> datetime:
    return datetime.now(MSK)


def get_current_day_start() -> float:
    """Начало текущего дня (02:00 MSK сегодня или вчера)."""
    now = now_msk()
    day_start = now.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if now < day_start:
        day_start -= timedelta(days=1)
    return day_start.timestamp()


def get_current_day_end() -> float:
    """Конец текущего дня (02:00 MSK завтра или сегодня)."""
    return get_current_day_start() + 86400


def get_previous_day_period() -> tuple[float, float]:
    """Предыдущий завершённый день."""
    day_start = get_current_day_start()
    return day_start - 86400, day_start


def get_current_week_start() -> float:
    """Начало текущей недели (понедельник 02:00 MSK)."""
    now = now_msk()
    # Текущий день с учётом сброса в 02:00
    effective_day = now.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if now < effective_day:
        effective_day -= timedelta(days=1)

    # Откатываемся до понедельника
    days_since_monday = effective_day.weekday()  # 0=пн
    week_start = effective_day - timedelta(days=days_since_monday)
    return week_start.timestamp()


def get_previous_week_period() -> tuple[float, float]:
    """Предыдущая завершённая неделя."""
    week_start = get_current_week_start()
    return week_start - 7 * 86400, week_start


def get_current_month_start() -> float:
    """Начало текущего месяца (1-е число 02:00 MSK)."""
    now = now_msk()
    effective_day = now.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if now < effective_day:
        effective_day -= timedelta(days=1)

    month_start = effective_day.replace(day=1)
    return month_start.timestamp()


def get_previous_month_period() -> tuple[float, float]:
    """Предыдущий завершённый месяц."""
    now = now_msk()
    effective_day = now.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if now < effective_day:
        effective_day -= timedelta(days=1)

    # Начало текущего месяца
    current_month_start = effective_day.replace(day=1)

    # Начало предыдущего месяца
    if current_month_start.month == 1:
        prev_month_start = current_month_start.replace(
            year=current_month_start.year - 1, month=12
        )
    else:
        prev_month_start = current_month_start.replace(
            month=current_month_start.month - 1
        )

    return prev_month_start.timestamp(), current_month_start.timestamp()


def get_next_report_time() -> datetime:
    """Следующее 02:00 MSK."""
    now = now_msk()
    target = now.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def is_week_reset(dt: datetime) -> bool:
    """Это понедельник 02:00?"""
    return dt.weekday() == 0


def is_month_reset(dt: datetime) -> bool:
    """Это 1-е число 02:00?"""
    return dt.day == 1


def calc_stats(stats: list) -> dict:
    """Рассчитать статистику из списка ордеров."""
    order_count = len(stats)
    if order_count > 0:
        prices = [s["price"] for s in stats if s["price"] > 0]
        volumes = [s["limits_max"] for s in stats if s["limits_max"] > 0]
        total_volume = sum(volumes)
        avg_price = sum(prices) / len(prices) if prices else 0.0
    else:
        total_volume = 0.0
        avg_price = 0.0

    return {
        "order_count": order_count,
        "total_volume": total_volume,
        "avg_price": avg_price,
    }


def format_volume(vol: float) -> str:
    return f"{vol:,.0f}".replace(",", " ")


def format_price(price: float) -> str:
    return f"{price:.2f}"