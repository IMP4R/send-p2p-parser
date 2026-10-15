import asyncio
import logging
import json
import time
from datetime import timedelta
from aiogram import Bot
from aiogram.types import (
    InlineKeyboardMarkup as IKM,
    InlineKeyboardButton as IKB
)

from send_client import SendTGClient
from channel_poster import ChannelPoster
from database import (
    get_tracking_offers, get_offer, update_offer_state,
    get_setting, get_template, record_order,
    get_stats_for_period, clear_stats_before,
    get_report_template, save_report_history
)
from stats_utils import (
    now_msk, get_current_day_start, get_previous_day_period,
    get_previous_week_period, get_previous_month_period,
    get_next_report_time, is_week_reset, is_month_reset,
    calc_stats, format_volume, format_price, MSK
)
from config import POLL_INTERVAL, ADMIN_IDS

logger = logging.getLogger(__name__)


class OfferMonitor:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.poster = ChannelPoster(bot)
        self.client = SendTGClient()
        self.running = False
        self._task = None
        self._report_task = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        self._report_task = asyncio.create_task(self._report_loop())
        logger.info(f"📡 Monitor started (interval={POLL_INTERVAL}s)")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        if self._report_task:
            self._report_task.cancel()
        logger.info("📡 Monitor stopped")

    # ═══ Основной цикл опроса ═══

    async def _loop(self):
        await asyncio.sleep(2)
        while self.running:
            try:
                await self._poll_all()
            except Exception as e:
                logger.error(f"Monitor error: {e}", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_all(self):
        offers = get_tracking_offers()
        if not offers:
            return

        channel_id = get_setting("channel_id")
        if not channel_id:
            logger.warning("❌ channel_id not set!")
            return

        channel_id = int(channel_id)

        for offer_row in offers:
            if not self.running:
                break
            offer_id = offer_row["offer_id"]
            try:
                await self._poll_offer(offer_id, offer_row, channel_id)
            except Exception as e:
                logger.error(f"Offer {offer_id} error: {e}", exc_info=True)
            await asyncio.sleep(0.1)

    async def _poll_offer(
        self, offer_id: int, offer_row: dict, channel_id: int
    ):
        data = self.client.get_offer(offer_id)

        if data is None:
            return

        status_code = data.get("statusCode")

        if status_code == 404:
            if offer_row["is_open"]:
                await self._close_offer(offer_id, offer_row, channel_id)
                update_offer_state(
                    offer_id, {}, "deleted", False,
                    "0", "0", "0", is_open=False
                )
            return

        if status_code == 401:
            logger.warning("401 — cookies expired!")
            return

        if status_code == 429:
            logger.warning("429 — rate limited, sleeping 30s")
            await asyncio.sleep(30)
            return

        if status_code and status_code != 200:
            return

        status = data.get("status", "")
        is_visible = data.get("is_visible", False)
        price = data.get("price", "0")
        limits = data.get("limits", {})
        limits_min = limits.get("min", "0")
        limits_max = limits.get("max", "0")

        is_open = (status == "active")
        was_open = bool(offer_row["is_open"])

        changed = False
        limits_changed = False

        if offer_row["last_status"] != status:
            changed = True
        if bool(offer_row.get("last_is_visible")) != is_visible:
            changed = True
        if offer_row.get("last_price") != price:
            changed = True
        if offer_row.get("last_limits_min") != limits_min:
            changed = True
            limits_changed = True
        if offer_row.get("last_limits_max") != limits_max:
            changed = True
            limits_changed = True

        first_poll = offer_row["last_data"] is None

        if first_poll:
            if is_open:
                self._record_new_order(offer_id, price, limits_min, limits_max)
                msg_id = await self._send_open(data, offer_id, channel_id)
                update_offer_state(
                    offer_id, data, status, is_visible,
                    price, limits_min, limits_max,
                    is_open=True, message_id=msg_id
                )
            else:
                update_offer_state(
                    offer_id, data, status, is_visible,
                    price, limits_min, limits_max, is_open=False
                )
            return

        # Случай 1: CLOSED → OPEN
        if not was_open and is_open:
            self._record_new_order(offer_id, price, limits_min, limits_max)
            msg_id = await self._send_open(data, offer_id, channel_id)
            update_offer_state(
                offer_id, data, status, is_visible,
                price, limits_min, limits_max,
                is_open=True, message_id=msg_id
            )

        # Случай 2: OPEN → CLOSED
        elif was_open and not is_open:
            await self._close_offer(offer_id, offer_row, channel_id)
            update_offer_state(
                offer_id, data, status, is_visible,
                price, limits_min, limits_max, is_open=False
            )

        # Случай 3: OPEN + изменения
        elif was_open and is_open and changed:
            if limits_changed:
                self._record_new_order(offer_id, price, limits_min, limits_max)

            await self._close_offer(offer_id, offer_row, channel_id)
            msg_id = await self._send_open(data, offer_id, channel_id)
            update_offer_state(
                offer_id, data, status, is_visible,
                price, limits_min, limits_max,
                is_open=True, message_id=msg_id
            )

        # Случай 4: OPEN без изменений
        elif was_open and is_open and not changed:
            update_offer_state(
                offer_id, data, status, is_visible,
                price, limits_min, limits_max,
                is_open=True, message_id=offer_row["channel_message_id"]
            )

        # Случай 5: CLOSED
        else:
            update_offer_state(
                offer_id, data, status, is_visible,
                price, limits_min, limits_max, is_open=False
            )

    def _record_new_order(
        self, offer_id: int, price: str, limits_min: str, limits_max: str
    ):
        try:
            p = float(price) if price else 0.0
            lmin = float(limits_min) if limits_min else 0.0
            lmax = float(limits_max) if limits_max else 0.0
            period_start = get_current_day_start()
            record_order(offer_id, p, lmin, lmax, period_start)
            logger.info(
                f"📊 New order: offer={offer_id}, price={p}, "
                f"limits={lmin}-{lmax}"
            )
        except (ValueError, TypeError) as e:
            logger.error(f"Record order error: {e}")

    # ═══ Ежедневный отчёт ═══

    async def _report_loop(self):
        await asyncio.sleep(5)

        while self.running:
            try:
                target = get_next_report_time()
                wait_seconds = (target - now_msk()).total_seconds()
                logger.info(
                    f"📊 Next report at "
                    f"{target.strftime('%Y-%m-%d %H:%M MSK')} "
                    f"(in {wait_seconds/3600:.1f}h)"
                )

                while wait_seconds > 0 and self.running:
                    sleep_time = min(wait_seconds, 30)
                    await asyncio.sleep(sleep_time)
                    wait_seconds -= sleep_time

                if not self.running:
                    break

                await self._send_reports()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Report loop error: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _send_reports(self):
        report_time = now_msk()
        logger.info(f"📊 Generating reports at {report_time}")

        report_tpl = get_report_template()
        template = report_tpl.get("template", "")
        send_to_channel = bool(report_tpl.get("send_to_channel", ''))

        if not template:
            template = (
                "✉️\n\n"
                "Статистика за 24ч :\n\n"
                "⚠️ Кол-во ордеров: <b>{order_count}</b>\n"
                "⚠️ Сумма средств: <b>{total_volume}</b>\n"
                "🛍 Средний курс: <b>{avg_price}</b>\n\n"
                "Увидимся завтра👍"
            )

        # Дневной
        day_start, day_end = get_previous_day_period()
        day_stats = get_stats_for_period(day_start, day_end)
        day_calc = calc_stats(day_stats)
        day_text = self._format_report(template, day_calc, "24ч")
        await self._broadcast_report(day_text, send_to_channel)
        save_report_history(
            "day", day_start, day_end,
            day_calc["order_count"],
            day_calc["total_volume"],
            day_calc["avg_price"]
        )

        # Недельный
        if is_week_reset(report_time):
            week_start, week_end = get_previous_week_period()
            week_stats = get_stats_for_period(week_start, week_end)
            week_calc = calc_stats(week_stats)
            week_text = (
                "📊 <b>Итоги за неделю:</b>\n\n"
                f"⚠️ Кол-во ордеров: <b>{week_calc['order_count']}</b>\n"
                f"⚠️ Сумма средств: <b>"
                f"{format_volume(week_calc['total_volume'])}</b>\n"
                f"🛍 Средний курс: <b>"
                f"{format_price(week_calc['avg_price'])}</b>"
            )
            await self._broadcast_report(week_text, send_to_channel)
            save_report_history(
                "week", week_start, week_end,
                week_calc["order_count"],
                week_calc["total_volume"],
                week_calc["avg_price"]
            )

        # Месячный
        if is_month_reset(report_time):
            month_start, month_end = get_previous_month_period()
            month_stats = get_stats_for_period(month_start, month_end)
            month_calc = calc_stats(month_stats)
            month_text = (
                "📊 <b>Итоги за месяц:</b>\n\n"
                f"⚠️ Кол-во ордеров: <b>{month_calc['order_count']}</b>\n"
                f"⚠️ Сумма средств: <b>"
                f"{format_volume(month_calc['total_volume'])}</b>\n"
                f"🛍 Средний курс: <b>"
                f"{format_price(month_calc['avg_price'])}</b>"
            )
            await self._broadcast_report(month_text, send_to_channel)
            save_report_history(
                "month", month_start, month_end,
                month_calc["order_count"],
                month_calc["total_volume"],
                month_calc["avg_price"]
            )

        clear_stats_before(time.time() - 35 * 86400)

    def _format_report(self, template: str, calc: dict, period: str) -> str:
        return template.replace(
            "{order_count}", str(calc["order_count"])
        ).replace(
            "{total_volume}", format_volume(calc["total_volume"])
        ).replace(
            "{avg_price}", format_price(calc["avg_price"])
        ).replace(
            "{period}", period
        )

    async def _broadcast_report(self, text: str, send_to_channel: bool):
        for admin_id in ADMIN_IDS:
            try:
                await self.bot.send_message(
                    chat_id=admin_id, text=text, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Report to admin {admin_id}: {e}")

        if send_to_channel:
            channel_id = get_setting("channel_id")
            if channel_id:
                await self.poster.send_text(int(channel_id), text)

    # ═══ Построение сообщений ═══

    def _build_message(self, data: dict, is_open: bool) -> str:
        tpl_data = get_template()
        template = tpl_data.get("template", "")

        offer_type = data.get("type", "sell")
        asset = data.get("asset", "USDT")
        fiat = data.get("fiat", "RUB")
        price = data.get("price", "0")
        limits = data.get("limits", {})

        try:
            price_float = float(price)
            price_str = f"{price_float:.2f}"
        except (ValueError, TypeError):
            price_str = str(price)

        replacements = {
            "{type_emoji}": "🟢" if offer_type == "buy" else "🔴",
            "{type_text}": "Покупка" if offer_type == "buy" else "Продажа",
            "{asset}": asset,
            "{fiat}": fiat,
            "{fiat_emoji}": "💵" if fiat == "USD" else "💶" if fiat == "EUR" else "💵",
            "{price}": price_str,
            "{min}": limits.get("min", "0"),
            "{max}": limits.get("max", "0"),
            "{status_emoji}": "🟢" if is_open else "🔴",
            "{status_text}": "Открыто" if is_open else "Закрыто",
            "{user_name}": data.get("user", {}).get("name", ""),
            "{user_rating}": str(data.get("user", {}).get("rating", "")),
            "{user_orders}": str(data.get("user", {}).get("orders", "")),
        }

        text = template
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    def _build_keyboard(self, offer_id: int) -> IKM:
        tpl = get_template()
        btn_text = tpl.get("button_text", "📋 Открыть оффер")
        btn_emoji_id = tpl.get("button_emoji_id")
        btn_style = tpl.get("button_style")

        url = f"https://t.me/send?start=O{offer_id}"
        btn_kwargs = {"text": btn_text, "url": url}
        if btn_emoji_id:
            btn_kwargs["icon_custom_emoji_id"] = btn_emoji_id
        if btn_style:
            btn_kwargs["style"] = btn_style

        return IKM(inline_keyboard=[[IKB(**btn_kwargs)]])

    async def _send_open(
        self, data: dict, offer_id: int, channel_id: int
    ) -> int | None:
        text = self._build_message(data, is_open=True)
        kb = self._build_keyboard(offer_id)
        msg_id = await self.poster.send_message(channel_id, text, kb)
        if msg_id:
            logger.info(f"📤 Offer {offer_id} OPEN → msg {msg_id}")
        return msg_id

    async def _close_offer(
        self, offer_id: int, offer_row: dict, channel_id: int
    ):
        msg_id = offer_row.get("channel_message_id")
        if not msg_id:
            return

        last_data = {}
        if offer_row.get("last_data"):
            try:
                last_data = json.loads(offer_row["last_data"])
            except Exception:
                pass

        text = self._build_message(last_data, is_open=False)
        kb = self._build_keyboard(offer_id)
        await self.poster.edit_message(channel_id, msg_id, text, kb)

    async def force_poll(self, offer_id: int) -> str:
        channel_id = get_setting("channel_id")
        if not channel_id:
            return "❌ Канал не настроен"
        offer_row = get_offer(offer_id)
        if not offer_row:
            return "❌ Оффер не найден в БД"
        try:
            await self._poll_offer(offer_id, offer_row, int(channel_id))
            return "✅ Опрошен"
        except Exception as e:
            return f"❌ {e}"