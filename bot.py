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
    MessageHandler,
    filters,
    ContextTypes,
)

TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
SHEET_URL     = os.getenv("SHEET_URL", "")

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

(
    MENU,
    WAIT_Q1, WAIT_Q2, WAIT_Q3, WAIT_Q4, WAIT_Q5,
) = range(6)

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


async def log_to_sheet(event: str, **kwargs):
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


async def delayed_pdf(bot, chat_id: int):
    await asyncio.sleep(3 * 60)
    with open(PDF_PATH, "rb") as f:
        await bot.send_document(
            chat_id=chat_id,
            document=f,
            filename="Эмоции и потребности.pdf",
            caption="📋 Полный список базовых эмоций и потребностей, которые есть у каждого человека",
        )

async def delayed_video_note(bot, chat_id: int):
    await asyncio.sleep(10 * 60)
    try:
        with open(VIDEO_NOTE_PATH, "rb") as f:
            await bot.send_video_note(chat_id=chat_id, video_note=f)
    except Exception as exc:
        logger.warning("Video note failed: %s", exc)
    await asyncio.sleep(2)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "Беспокоит нерешённый вопрос в личной или деловой сфере?\n\n"
                "Приглашаю тебя на бесплатную диагностику, где за 30 минут ты получишь:\n\n"
                "· ясный ответ на свой запрос\n"
                "· индивидуальные рекомендации: как именно тебе стоит развивать интуицию, "
                "чтобы больше не прибегать к советникам"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Записаться на диагностику",
                    url="https://t.me/svami_assistent?text=Здравствуйте%2C+хочу+записаться+к+Марии+на+бесплатную+диагностику"
                ),
            ]]),
        )
    except Exception as exc:
        logger.warning("Diagnostics link message failed: %s", exc)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user = update.message.from_user
    asyncio.create_task(log_to_sheet(
        "start",
        name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
        username=f"@{user.username}" if user.username else "",
        user_id=user.id,
    ))
    await update.message.reply_text(
        "Привет! 👋\n\nЯ бот Марии Альпидовской, эксперта по развитию сознания и интуиции "
        "для принятия точных решений в деловых и личных вопросах.\n\n"
        "Ниже тест из 5 вопросов 👇\nОн поможет определить уровень развития твоей интуиции прямо сейчас.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅  Пройти тест на интуицию", callback_data="m_test")],
        ]),
    )
    return MENU


async def ask_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data["score"] = 0
    context.user_data["current_step"] = "1 · Начал тест (увидел В1)"
    asyncio.create_task(log_to_sheet("q1_shown",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))
    with open_img("q1") as img:
        await q.message.reply_photo(photo=img,
            caption="*Вопрос 1 из 5*\n\nПосмотри на три фигуры. Не думай, просто почувствуй:\nкто из них прямо сейчас переживает радость?",
            parse_mode="Markdown", reply_markup=abc_kb("q1"))
    return WAIT_Q1


async def answer_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q1", q.data.split("_")[1])
    context.user_data["current_step"] = "3 · Ответил на В1"
    asyncio.create_task(log_to_sheet("q1_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))
    with open_img("q2") as img:
        await q.message.reply_photo(photo=img,
            caption="*Вопрос 2 из 5*\n\nПосмотрите на эту карточку 5 секунд. Что вы замечаете первым?\n\nА — Что-то в поведении или взгляде одного из них\nБ — Обычная рабочая встреча\nВ — Ничего особенного не замечаю",
            parse_mode="Markdown", reply_markup=abc_kb("q2"))
    return WAIT_Q2


async def answer_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q2", q.data.split("_")[1])
    context.user_data["current_step"] = "4 · Ответил на В2"
    asyncio.create_task(log_to_sheet("q2_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))
    with open_img("q3") as img:
        await q.message.reply_photo(photo=img,
            caption="*Вопрос 3 из 5*\n\nНа одной из этих карточек — животное.\nНе угадывай, почувствуй, на какой из трёх?",
            parse_mode="Markdown", reply_markup=abc_kb("q3"))
    return WAIT_Q3


async def answer_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q3", q.data.split("_")[1])
    context.user_data["current_step"] = "5 · Ответил на В3"
    asyncio.create_task(log_to_sheet("q3_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))
    with open_img("q4") as img:
        await q.message.reply_photo(photo=img,
            caption="*Вопрос 4 из 5*\n\nКакая погода за дверью?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("А — Солнечное лето ☀️", callback_data="q4_a")],
                [InlineKeyboardButton("Б — Дождливая осень 🌧", callback_data="q4_b")],
                [InlineKeyboardButton("В — Снежная зима ❄️", callback_data="q4_c")],
            ]))
    return WAIT_Q4


async def answer_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q4", q.data.split("_")[1])
    context.user_data["current_step"] = "6 · Ответил на В4"
    asyncio.create_task(log_to_sheet("q4_done",
        name=f"{q.from_user.first_name or ''} {q.from_user.last_name or ''}".strip(),
        username=f"@{q.from_user.username}" if q.from_user.username else "",
        user_id=q.from_user.id,
    ))
    with open_img("q5") as img:
        await q.message.reply_photo(photo=img,
            caption="*Вопрос 5 из 5* — последний 👌\n\nКакая из этих картинок точнее описывает твоё внутреннее состояние, когда нужно принять важное решение?\n\nА — Правая. Умею находить тишину внутри\nБ — Зависит от ситуации\nВ — Левая. Шум, тревога",
            parse_mode="Markdown", reply_markup=abc_kb("q5"))
    return WAIT_Q5


async def answer_q5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q5", q.data.split("_")[1])
    context.user_data["current_step"] = "8 · Получил результат ✅"
    total = context.user_data.get("score", 0)

    if total >= 8:
        title = "🔮 Интуиция включена"
        body  = "Вы умеете слышать себя — даже когда снаружи шум. Интуиция — это тренируемый навык, и у тебя он уже хорошо развит."
        tier = f"🔮 Интуиция включена ({total}/10)"
    elif total >= 4:
        title = "⚡️ Интуиция нестабильна"
        body  = "Иногда вы чувствуете точно. Интуиция есть, но канал нестабилен. Твой сигнал уже есть — его нужно просто настроить."
        tier = f"⚡️ Интуиция нестабильна ({total}/10)"
    else:
        title = "🌱 Сигнал сложно услышать"
        body  = "Интуиция есть у каждого — просто сейчас к ней сложно пробиться. Твой сигнал никуда не исчез."
        tier = f"🌱 Сигнал сложно услышать ({total}/10)"

    context.user_data["test_result_summary"] = tier
    from_user = q.from_user
    asyncio.create_task(log_to_sheet("q5_done",
        name=f"{from_user.first_name or ''} {from_user.last_name or ''}".strip(),
        username=f"@{from_user.username}" if from_user.username else "",
        user_id=from_user.id,
    ))
    asyncio.create_task(log_to_sheet("result",
        name=f"{from_user.first_name or ''} {from_user.last_name or ''}".strip(),
        username=f"@{from_user.username}" if from_user.username else "",
        user_id=from_user.id,
        result=tier,
    ))

    await q.message.reply_text(
        "✅ *Правильные ответы:*\n\nВопрос 1 – радость переживала А, девушка слева\n"
        "Вопрос 2 – один из участников встречи действительно испытывает давление\n"
        "Вопрос 3 – животное было на карточке В — слон 🐘\n"
        "Вопрос 4 – за дверью солнечное лето ☀️\n"
        "Вопрос 5 – умение управлять своим вниманием позволяет более точно считывать информацию",
        parse_mode="Markdown",
    )

    with open(IMG["otvet_1"], "rb") as f1, open(IMG["otvet_3"], "rb") as f3, open(IMG["otvet_4"], "rb") as f4:
        await context.bot.send_media_group(
            chat_id=q.message.chat_id,
            media=[InputMediaPhoto(f1), InputMediaPhoto(f3), InputMediaPhoto(f4)],
        )

    await q.message.reply_text(
        f"*Твой результат: {total} из 10 баллов*\n\n*{title}*\n\n{body}",
        parse_mode="Markdown",
    )

    chat_id_for_yt = q.message.chat_id
    bot_ref = context.bot
    async def send_youtube():
        await asyncio.sleep(5)
        await bot_ref.send_message(chat_id=chat_id_for_yt,
            text=f"🎥 *Как считывать намерение человека*\n\nСмотрите в бесплатном уроке:\n\nУрок по ссылке👇\n{TECHNIQUE_URL}",
            parse_mode="Markdown")
    asyncio.create_task(send_youtube())

    chat_id = q.message.chat_id
    asyncio.create_task(delayed_pdf(context.bot, chat_id))
    asyncio.create_task(delayed_video_note(context.bot, chat_id))

    try:
        await notify_admin(context, user=from_user, test_result=tier)
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)

    return MENU


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.message.from_user
    text = update.message.text
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    tg   = f"@{user.username}" if user.username else "нет username"
    step_label = context.user_data.get("current_step", "неизвестно")
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(f"💬 *Сообщение от пользователя*\n\n👤 {name}\n📱 {tg}  |  ID: `{user.id}`\n📍 Шаг воронки: {step_label}\n\n✏️ {text}"),
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.warning("Admin free-text notify failed: %s", exc)
    asyncio.create_task(log_to_sheet("free_text",
        name=name,
        username=f"@{user.username}" if user.username else "",
        user_id=user.id,
        message=text[:500],
        step=step_label,
    ))


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


def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(ask_q1, pattern="^m_test$"),
                CallbackQueryHandler(program_info_callback, pattern="^program_info$"),
            ],
            WAIT_Q1: [CallbackQueryHandler(answer_q1, pattern="^q1_")],
            WAIT_Q2: [CallbackQueryHandler(answer_q2, pattern="^q2_")],
            WAIT_Q3: [CallbackQueryHandler(answer_q3, pattern="^q3_")],
            WAIT_Q4: [CallbackQueryHandler(answer_q4, pattern="^q4_")],
            WAIT_Q5: [CallbackQueryHandler(answer_q5, pattern="^q5_")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    logger.info("Бот запущен ✓")
    app.run_polling()


if __name__ == "__main__":
    main()
