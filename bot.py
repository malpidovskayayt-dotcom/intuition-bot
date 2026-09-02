#!/usr/bin/env python3
"""
Бот Марии Альпидовской — тест на интуицию
"""

import asyncio
import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
TOKEN         = os.getenv("BOT_TOKEN", "8895251334:AAGggr3X-6g5ZmNuFCAb6WhkOjCfQujRzJY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

TECHNIQUE_URL = "https://youtu.be/tT9jt072jQw?si=RIIoirofvHC53WzY"

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
    WAIT_TEST_CONTACT,
    SHOW_RESULT,
) = range(8)

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

async def notify_admin(context, user, contact_str: str, test_result):
    if not ADMIN_CHAT_ID:
        return
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    tg   = f"@{user.username}" if user.username else "нет username"
    text = (
        "🆕 *Новый контакт из бота*\n\n"
        f"👤 {name}\n"
        f"📱 {tg}  |  ID: `{user.id}`\n"
        f"📞 Контакт: {contact_str}\n"
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
    await asyncio.sleep(10 * 60)   # 10 мин после видео (= 7 мин после PDF)
    with open(VIDEO_NOTE_PATH, "rb") as f:
        await bot.send_video_note(chat_id=chat_id, video_note=f)
    await bot.send_message(
        chat_id=chat_id,
        text='Онлайн-курс "Основы управления интуицией"\nв записи с моей обратной связью\n\nСтарт 10 сентября',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📚 Узнать программу курса", callback_data="program_info"),
        ]]),
    )
    logger.info("Video note + button sent to chat %s", chat_id)


# ══════════════════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я бот Марии Альпидовской, эксперта по развитию сознания и интуиции "
        "для принятия точных решений в деловых и личных вопросах.\n\n"
        "Ниже тест из 5 вопросов 👇\n"
        "Он поможет определить уровень развития твоей интуиции прямо сейчас.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔮  Пройти тест на интуицию", callback_data="m_test")],
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
# ПОСЛЕ ВОПРОСА 5 → ЗАПРОС КОНТАКТА
# ══════════════════════════════════════════════════════════════════════════════
async def ask_contact_after_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q5", q.data.split("_")[1])

    await q.message.reply_text(
        "✅ Отлично, тест пройден!\n\n"
        "Чтобы я смог отправить тебе результаты, поделись, пожалуйста, контактом 👇",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]],
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
    )
    return WAIT_TEST_CONTACT


# ══════════════════════════════════════════════════════════════════════════════
# ПОЛУЧЕНИЕ КОНТАКТА → РЕЗУЛЬТАТЫ + ОТЛОЖЕННЫЕ ЗАДАЧИ
# ══════════════════════════════════════════════════════════════════════════════
async def handle_test_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = update.message.contact
    phone   = contact.phone_number if contact else "не передан"
    cname   = f"{contact.first_name or ''} {contact.last_name or ''}".strip() if contact else ""
    contact_str = phone + (f" ({cname})" if cname else "")

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

    # Уведомляем администратора
    await notify_admin(
        context,
        user=update.message.from_user,
        contact_str=contact_str,
        test_result=tier,
    )

    # Убираем клавиатуру
    await update.message.reply_text("Спасибо! ✅", reply_markup=ReplyKeyboardRemove())

    # 1 — правильные ответы
    await update.message.reply_text(
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
            chat_id=update.message.chat_id,
            media=[
                InputMediaPhoto(f1),
                InputMediaPhoto(f3),
                InputMediaPhoto(f4),
            ],
        )

    # 3 — результат по баллам
    await asyncio.sleep(5)
    await update.message.reply_text(
        f"*Твой результат: {total} из 10 баллов*\n\n"
        f"*{title}*\n\n{body}",
        parse_mode="Markdown",
    )

    # 4 — бесплатный урок (YouTube)
    await asyncio.sleep(10)
    await update.message.reply_text(
        "🎥 *Как считывать намерение человека*\n\n"
        "Мария подготовила бесплатный урок, в котором разбирает технику "
        "точного считывания намерений: в переговорах, при знакомстве с "
        "партнёром, в момент важного решения.\n\n"
        "Урок по ссылке👇\n"
        f"{TECHNIQUE_URL}\n\n"
        "0:00 Почему мы ошибаемся в людях\n"
        "0:35 Слова и намерение — в чём разница\n"
        "1:30 3 уровня считывания человека\n"
        "3:10 Шаг 1: выйти в позицию наблюдателя\n"
        "4:20 Шаг 2: правильные внутренние вопросы\n"
        "5:30 Шаг 3: перестать читать буквально\n"
        "7:00 Что делать с полученной информацией\n"
        "9:15 Как развить этот навык системно",
        parse_mode="Markdown",
    )

    # ─ Запускаем отложенные задачи ────────────────────────────────────────
    chat_id = update.message.chat_id
    asyncio.create_task(delayed_pdf(context.bot, chat_id))
    asyncio.create_task(delayed_video_note(context.bot, chat_id))

    logger.info("User %s finished test. Score: %d, phone: %s", update.message.from_user.id, total, phone)
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
            WAIT_Q5: [CallbackQueryHandler(ask_contact_after_test, pattern="^q5_")],
            WAIT_TEST_CONTACT: [
                MessageHandler(filters.CONTACT, handle_test_contact),
            ],
            SHOW_RESULT: [],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    logger.info("Бот запущен ✓")
    app.run_polling()


if __name__ == "__main__":
    main()
