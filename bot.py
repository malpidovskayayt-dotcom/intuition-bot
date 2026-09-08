#!/usr/bin/env python3
"""
Бот Марии Альпидовской — тест на интуицию
"""

import asyncio
import os
import logging
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
SHEET_URL     = os.getenv("SHEET_URL", "")   # Google Apps Script URL

TECHNIQUE_URL = "https://youtu.be/iDxW8sOII98?si=jBROUhrJdAUriJMK"

BASE = os.path.join(os.path.dirname(__file__), "images")
IMG = {
    "q1":      f"{BASE}/vopros_1.jpg",
    "q2":      f"{BASE}/vopros_2.jpg",
    "q3":      f"{BASE}/vopros_3.jpg",
    "q4":      f"{BASE}/vopros_4.jpg",
    "q5":      f"{BASE}/vopros_5.jpg",
    "otvet_1": f"{BASE}/otvet_1.jpg",
    "otvet_3": f"{BASE}/otvet_3.jpg",
    "otvet_4": f"{BASE}/otvet_4.jpg",
}

PDF_PATH        = os.path.join(os.path.dirname(__file__), "Эмоции и потребности.pdf")
VIDEO_NOTE_PATH = os.path.join(os.path.dirname(__file__), "kruzhok.mp4")

# ─── СОСТОЯНИЯ ────────────────────────────────────────────────────────────────
(
    MENU,
    WAIT_Q1, WAIT_Q2, WAIT_Q3, WAIT_Q4, WAIT_Q5,
) = range(6)

# ─── ОЧКИ ─────────────────────────────────────────────────────────────────────
SCORES = {
    "q1": {"a": 2, "b": 0, "c": 0},
    "q2": {"a": 2, "b": 1, "c": 0},
    "q3": {"a": 0, "b": 0, "c": 2},
    "q4": {"a": 2, "b": 0, "c": 0},
    "q5": {"a": 2, "b": 1, "c": 0},
}

logging.basicConfig(
    format="%(asctime)s · %(name)s · %(levelname)s · %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────
async def log_to_sheet(event: str, **kwargs):
    """Отправляет событие в Google Sheets через Apps Script. Не блокирует бота."""
    if not SHEET_URL:
        return
    try:
        params = {"event": event, **{k: str(v) for k, v in kwargs.items()}}
        async with aiohttp.ClientSession() as session:
            await session.post(
                SHEET_URL, data=params,
                timeout=aiohttp.ClientTimeout(total=6),
                allow_redirects=True,
            )
    except Exception as exc:
        logger.warning("Sheet log skipped: %s", exc)


# ─── ВСПОМОГАТЕЛЬНЫЕ ──────────────────────────────────────────────────────────
def open_img(key: str):
    return open(IMG[key], "rb")

def abc_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("А", callback_data=f"{prefix}_a"),
        InlineKeyboardButton("Б", callback_data=f"{prefix}_b"),
        InlineKeyboardButton("В", callback_data=f"{prefix}_c"),
    ]])

def add_score(context, key: str, answer: str):
    context.user_data["score"] = context.user_data.get("score", 0) + SCORES[key][answer]

async def notify_admin(context, user, test_result):
    if not ADMIN_CHAT_ID:
        return
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    tg   = f"@{user.username}" if user.username else "нет username"
    text = (
        "🆕 *Новый результат из бота*\n\n"
        f"👤 {name}\n"
        f"📱 {tg}  |  ID: `{user.id}`\n"
        f"🧠 Результат теста: {test_result}"
    )
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="Markdown")


# ─── ОТЛОЖЕННЫЕ ЗАДАЧИ (asyncio tasks) ───────────────────────────────────────
async def delayed_pdf(bot, chat_id: int):
    await asyncio.sleep(3 * 60)
    with open(PDF_PATH, "rb") as f:
        await bot.send_document(
            chat_id=chat_id,
            document=f,
            filename="Эмоции и потребности.pdf",
            caption="📋 Полный список базовых эмоций и потребностей, которые есть у каждого человека",
        )
    logger.info("PDF sent to chat %s", chat_id)


async def delayed_video_note(bot, chat_id: int):
    await asyncio.sleep(10 * 60)   # 10 мин после PDF
    # 1 — сначала кружок
    try:
        with open(VIDEO_NOTE_PATH, "rb") as f:
            await bot.send_video_note(chat_id=chat_id, video_note=f)
    except Exception as exc:
        logger.warning("Video note failed: %s", exc)
    await asyncio.sleep(2)   # небольшая пауза, чтобы кружок дошёл раньше текста
    # 2 — потом сообщение с кнопкой
    try:
        await bot.send_message(
            chat_id=chat_id,
            text='Онлайн-курс «Основы управления интуицией»\nв записи с моей обратной связью',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📚 Узнать программу курса", url="https://maria-alpidovskaya.ru/online_kurs/"),
            ]]),
        )
    except Exception as exc:
        logger.warning("Course link message failed: %s", exc)
    logger.info("Video note + button sent to chat %s", chat_id)


# ══════════════════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    # Логируем запуск бота
    user = update.message.from_user
    asyncio.create_task(log_to_sheet(
        "start",
        name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
        username=f"@{user.username}" if user.username else "",
        user_id=user.id,
    ))
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я бот Марии Альпидовской, эксперта по развитию сознания и интуиции "
        "для принятия точных решений в деловых и личных вопросах.\n\n"
        "Ниже тест из 5 вопросов 👇\n"
        "Он поможет определить уровень развития твоей интуиции прямо сейчас.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅  Пройти тест на интуицию", callback_data="m_test")],
        ]),
    )
    return MENU


# ══════════════════════════════════════════════════════════════════════════════
# ВОПРОСЫ
# ══════════════════════════════════════════════════════════════════════════════
async def ask_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data["score"] = 0
    asyncio.create_task(log_to_sheet(
        "q1_shown",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))

    with open_img("q1") as img:
        await q.message.reply_photo(
            photo=img,
            caption=(
                "*Вопрос 1 из 5*\n\n"
                "Посмотри на три фигуры. Не думай, просто почувствуй:\n"
                "кто из них прямо сейчас переживает радость?"
            ),
            parse_mode="Markdown",
            reply_markup=abc_kb("q1"),
        )
    return WAIT_Q1


async def answer_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q1", q.data.split("_")[1])
    asyncio.create_task(log_to_sheet(
        "q1_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))

    with open_img("q2") as img:
        await q.message.reply_photo(
            photo=img,
            caption=(
                "*Вопрос 2 из 5*\n\n"
                "Посмотрите на эту карточку 5 секунд. "
                "Что вы замечаете первым?\n\n"
                "А — Что-то в поведении или взгляде одного из них. "
                "Не уверен что именно, но чувствую напряжение\n\n"
                "Б — Обычная рабочая встреча. "
                "Смотрю на детали: позы, жесты, обстановку\n\n"
                "В — Ничего особенного не замечаю. "
                "Сложно что-то «считать» по картинке"
            ),
            parse_mode="Markdown",
            reply_markup=abc_kb("q2"),
        )
    return WAIT_Q2


async def answer_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q2", q.data.split("_")[1])
    asyncio.create_task(log_to_sheet(
        "q2_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))

    with open_img("q3") as img:
        await q.message.reply_photo(
            photo=img,
            caption=(
                "*Вопрос 3 из 5*\n\n"
                "На одной из этих карточек — животное.\n"
                "Не угадывай, почувствуй, на какой из трёх?"
            ),
            parse_mode="Markdown",
            reply_markup=abc_kb("q3"),
        )
    return WAIT_Q3


async def answer_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q3", q.data.split("_")[1])
    asyncio.create_task(log_to_sheet(
        "q3_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))

    with open_img("q4") as img:
        await q.message.reply_photo(
            photo=img,
            caption=(
                "*Вопрос 4 из 5*\n\n"
                "Какая погода за дверью?"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("А — Солнечное лето ☀️",  callback_data="q4_a")],
                [InlineKeyboardButton("Б — Дождливая осень 🌧", callback_data="q4_b")],
                [InlineKeyboardButton("В — Снежная зима ❄️",    callback_data="q4_c")],
            ]),
        )
    return WAIT_Q4


async def answer_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q4", q.data.split("_")[1])
    asyncio.create_task(log_to_sheet(
        "q4_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))

    with open_img("q5") as img:
        await q.message.reply_photo(
            photo=img,
            caption=(
                "*Вопрос 5 из 5* — последний 👌\n\n"
                "Какая из этих картинок точнее описывает твоё внутреннее "
                "состояние, когда нужно принять важное решение?\n\n"
                "А — Правая. Умею находить тишину внутри, "
                "даже когда снаружи давление\n\n"
                "Б — Зависит от ситуации. Бывает и так, и так\n\n"
                "В — Левая. В моменте решения: шум, тревога, "
                "сложно услышать себя"
            ),
            parse_mode="Markdown",
            reply_markup=abc_kb("q5"),
        )
    return WAIT_Q5


# ══════════════════════════════════════════════════════════════════════════════
# ОТВЕТ НА ВОПРОС 5 → СРАЗУ РЕЗУЛЬТАТЫ + ОТЛОЖЕННЫЕ ЗАДАЧИ
# ══════════════════════════════════════════════════════════════════════════════
async def answer_q5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q5", q.data.split("_")[1])

    total = context.user_data.get("score", 0)

    # Определяем результат
    if total >= 8:
        title = "🔮 Интуиция включена"
        body  = (
            "Вы умеете слышать себя — даже когда снаружи шум. "
            "Замечаете то, что другие пропускают, и доверяете внутреннему сигналу.\n\n"
            "Интуиция — это тренируемый навык, и у тебя он уже хорошо развит. "
            "Следующий шаг — научиться использовать его системно: "
            "в переговорах, ключевых решениях, работе с людьми."
        )
        tier = f"🔮 Интуиция включена ({total}/10)"
    elif total >= 4:
        title = "⚡️ Интуиция нестабильна"
        body  = (
            "Иногда вы чувствуете точно и замечаете то, что другие не видят. "
            "Иногда — теряетесь в шуме собственных мыслей. "
            "Интуиция есть, но канал нестабилен.\n\n"
            "Интуиция — это тренируемый навык, который способен развить каждый. "
            "Твой сигнал уже есть — его нужно просто настроить, "
            "чтобы он работал не иногда, а каждый раз."
        )
        tier = f"⚡️ Интуиция нестабильна ({total}/10)"
    else:
        title = "🌱 Сигнал сложно услышать"
        body  = (
            "Интуиция есть у каждого — просто сейчас к ней сложно пробиться. "
            "Слишком много логики, анализа или внешних ориентиров. "
            "Это не навсегда.\n\n"
            "Интуиция — это тренируемый навык, который способен развить каждый. "
            "Твой сигнал никуда не исчез — он просто ждёт, "
            "когда ты научишься его слышать."
        )
        tier = f"🌱 Сигнал сложно услышать ({total}/10)"

    context.user_data["test_result_summary"] = tier

    # Логируем завершение теста в Google Sheets
    from_user = q.from_user
    asyncio.create_task(log_to_sheet(
        "q5_done",
        name=f"{from_user.first_name or ''} {from_user.last_name or ''}".strip(),
        username=f"@{from_user.username}" if from_user.username else "",
        user_id=from_user.id,
    ))
    asyncio.create_task(log_to_sheet(
        "result",
        name=f"{from_user.first_name or ''} {from_user.last_name or ''}".strip(),
        username=f"@{from_user.username}" if from_user.username else "",
        user_id=from_user.id,
        result=tier,
    ))

    # 1 — правильные ответы
    await q.message.reply_text(
        "✅ *Правильные ответы:*\n\n"
        "Вопрос 1 – радость переживала А, девушка слева\n"
        "Вопрос 2 – один из участников встречи действительно испытывает давление со стороны других участников\n"
        "Вопрос 3 – животное было на карточке В — слон 🐘\n"
        "Вопрос 4 – за дверью солнечное лето ☀️\n"
        "Вопрос 5 – умение управлять своим вниманием вне зависимости от внешней ситуации позволяет более точно считывать информацию с помощью интуиции",
        parse_mode="Markdown",
    )

    # 2 — три фото
    with open(IMG["otvet_1"], "rb") as f1, \
         open(IMG["otvet_3"], "rb") as f3, \
         open(IMG["otvet_4"], "rb") as f4:
        await context.bot.send_media_group(
            chat_id=q.message.chat_id,
            media=[
                InputMediaPhoto(f1),
                InputMediaPhoto(f3),
                InputMediaPhoto(f4),
            ],
        )

    # 3 — результат по баллам (сразу, без задержки)
    await q.message.reply_text(
        f"*Твой результат: {total} из 10 баллов*\n\n"
        f"*{title}*\n\n{body}",
        parse_mode="Markdown",
    )

    # 4 — бесплатный урок (YouTube) — через задачу, не блокируем
    chat_id_for_yt = q.message.chat_id
    bot_ref = context.bot
    async def send_youtube():
        await asyncio.sleep(5)
        await bot_ref.send_message(
            chat_id=chat_id_for_yt,
            text=(
                "🎥 *Как считывать намерение человека*\n\n"
                "Смотрите в бесплатном уроке:\n\n"
                "0:00 Почему мы ошибаемся в людях\n"
                "0:35 Слова и намерение — в чём разница\n"
                "1:30 3 уровня считывания человека\n"
                "3:10 Шаг 1: выйти в позицию наблюдателя\n"
                "4:20 Шаг 2: правильные внутренние вопросы\n"
                "5:30 Шаг 3: перестать читать буквально\n"
                "7:00 Что делать с полученной информацией\n"
                "8:30 Почему это не работает в стрессе\n"
                "9:15 Как развить этот навык системно\n\n"
                f"Урок по ссылке👇\n{TECHNIQUE_URL}"
            ),
            parse_mode="Markdown",
        )
    asyncio.create_task(send_youtube())

    # ─ Запускаем отложенные задачи ────────────────────────────────────────
    chat_id = q.message.chat_id
    asyncio.create_task(delayed_pdf(context.bot, chat_id))
    asyncio.create_task(delayed_video_note(context.bot, chat_id))

    # Уведомляем администратора
    try:
        await notify_admin(context, user=from_user, test_result=tier)
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)

    logger.info("User %s finished test. Score: %d", from_user.id, total)
    return MENU


# ══════════════════════════════════════════════════════════════════════════════
# КНОПКА «Узнать программу курса» → сразу ссылка (контакт уже есть)
# ══════════════════════════════════════════════════════════════════════════════
async def program_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "Онлайн-курс «Основы управления интуицией» — все подробности и запись здесь:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 Перейти на сайт", url="https://maria-alpidovskaya.ru/online_kurs/"),
        ]]),
    )
    return MENU


# ══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(ask_q1,               pattern="^m_test$"),
                CallbackQueryHandler(program_info_callback, pattern="^program_info$"),
            ],
            WAIT_Q1: [CallbackQueryHandler(answer_q1,              pattern="^q1_")],
            WAIT_Q2: [CallbackQueryHandler(answer_q2,              pattern="^q2_")],
            WAIT_Q3: [CallbackQueryHandler(answer_q3,              pattern="^q3_")],
            WAIT_Q4: [CallbackQueryHandler(answer_q4,              pattern="^q4_")],
            WAIT_Q5: [CallbackQueryHandler(answer_q5, pattern="^q5_")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    logger.info("Бот запущен ✓")
    app.run_polling()


if __name__ == "__main__":
    main()
