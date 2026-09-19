#!/usr/bin/env python3
"""
Тестовый бот для проверки оплаты — Мария Альпидовская
Флоу: /start → кружочек → описание курса → спецусловие → оплата
"""

import asyncio
import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Переменные окружения ───────────────────────────────────────────────────────
TOKEN                  = os.environ["BOT_TOKEN"]
PAYMENT_PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")
ADMIN_CHAT_ID          = os.environ.get("ADMIN_CHAT_ID", "")
VIDEO_NOTE_PATH        = "kruzhok.mp4"

# ── Тексты ────────────────────────────────────────────────────────────────────
COURSE_TEXT = (
    "✨ *Курс «Управление интуицией»*\n\n"
    "За 4 недели ты освоишь воспроизводимый навык считывания "
    "информации и ситуаций — не случайное озарение, а техника.\n\n"
    "*После курса ты сможешь:*\n\n"
    "· Считывать людей — эмоции, намерения, скрытые мотивы\n"
    "· Принимать точные решения когда данных и времени мало\n"
    "· Прогнозировать исходы переговоров, партнёрств, сделок\n"
    "· Доверять первому ощущению — и не ошибаться\n"
    "· Видеть на шаг вперёд в бизнесе и личной жизни\n\n"
    "*Что включено:*\n"
    "— 6 живых + 4 онлайн встречи с практикой и разбором\n"
    "— 21 ежедневное задание до 30 минут\n"
    "— 10+ практик на развитие интуиции\n"
    "— Обратная связь по каждому заданию\n"
    "— Поддержка в чате весь курс\n\n"
    "📅 Старт — *30 сентября*"
)

PRICE_TEXT = (
    "🔥 *Специальные условия для тебя*\n\n"
    "Стандартная цена курса: *7 990 ₽*\n\n"
    "В ближайшие *60 минут* цена курса для тебя:\n"
    "→ *3 990 ₽*  \\(скидка 4 000 ₽\\)\n\n"
    "После — стоимость вернётся к стандартной 🕐"
)

SUCCESS_TEXT = (
    "✅ *Оплата прошла\\!*\n\n"
    "Мария свяжётся с тобой в ближайшее время\\.\n"
    "Все материалы и ссылки пришлём перед стартом курса 30 сентября 🎉\n\n"
    "Если вопросы — пиши: @maria\\_alpidovskaya"
)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Старт: сразу кружочек, потом описание курса."""
    chat_id = update.effective_chat.id

    # 1. Кружочек
    try:
        with open(VIDEO_NOTE_PATH, "rb") as f:
            await context.bot.send_video_note(chat_id=chat_id, video_note=f)
        await asyncio.sleep(2)
    except FileNotFoundError:
        logger.warning("Кружочек не найден: %s", VIDEO_NOTE_PATH)

    # 2. (Опционально) Фото-скриншоты того, что включает курс
    # Раскомментируй и добавь реальные файлы на сервер:
    #
    # photos = ["slide1.jpg", "slide2.jpg", "slide3.jpg"]
    # existing = [p for p in photos if os.path.exists(p)]
    # if existing:
    #     media = [InputMediaPhoto(open(p, "rb")) for p in existing]
    #     await context.bot.send_media_group(chat_id=chat_id, media=media)
    #     await asyncio.sleep(1)

    # 3. Текст с описанием + кнопка
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔥 Активировать спецусловие",
            callback_data="activate_special",
        )
    ]])

    await context.bot.send_message(
        chat_id=chat_id,
        text=COURSE_TEXT,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def activate_special(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Нажали «Активировать спецусловие» — показываем цену."""
    query = update.callback_query
    await query.answer("🔥 Спецусловие активировано!")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💳 Оплатить курс — 3 990 ₽",
            callback_data="pay_course",
        )
    ]])

    await query.message.reply_text(
        PRICE_TEXT,
        parse_mode="MarkdownV2",
        reply_markup=keyboard,
    )


async def pay_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Нажали «Оплатить» — отправляем счёт через ЮКасса."""
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if not PAYMENT_PROVIDER_TOKEN:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Оплата не настроена.\n"
                "Добавь PAYMENT_PROVIDER_TOKEN в переменные окружения."
            ),
        )
        return

    await context.bot.send_invoice(
        chat_id=chat_id,
        title="Курс «Управление интуицией»",
        description="4 недели · 6+4 встречи · 21 задание с разбором",
        payload="course_intuition_3990",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice("Спецусловие — курс", 399000)],  # 3990 ₽ в копейках
        start_parameter="course_payment",
        need_name=True,
        need_phone_number=True,
        need_email=False,
    )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обязательное подтверждение от бота перед списанием."""
    await update.pre_checkout_query.answer(ok=True)


async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Успешная оплата — уведомляем пользователя и администратора."""
    payment = update.message.successful_payment
    user    = update.effective_user
    name    = payment.order_info.name if payment.order_info else "—"
    phone   = payment.order_info.phone_number if payment.order_info else "—"
    amount  = payment.total_amount // 100

    # Уведомление администратору
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"✅ НОВАЯ ОПЛАТА!\n\n"
                    f"Пользователь: @{user.username} (id: {user.id})\n"
                    f"Имя: {name}\n"
                    f"Тел: {phone}\n"
                    f"Сумма: {amount} ₽"
                ),
            )
        except Exception as e:
            logger.warning("Не удалось уведомить админа: %s", e)

    # Сообщение пользователю
    await update.message.reply_text(
        SUCCESS_TEXT,
        parse_mode="MarkdownV2",
    )


# ── Запуск ────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(activate_special, pattern="^activate_special$"))
    app.add_handler(CallbackQueryHandler(pay_course, pattern="^pay_course$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

    logger.info("Тестовый бот запущен ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
