#!/usr/bin/env python3
"""
Бот Марии Альпидовской — тест на интуицию
"""

import asyncio
import os
import logging
import aiohttp
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
TOKEN             = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID     = os.getenv("ADMIN_CHAT_ID", "")
SHEET_URL         = os.getenv("SHEET_URL", "")         # Google Apps Script URL
YOOKASSA_TOKEN    = os.getenv("YOOKASSA_TOKEN", "")    # provider_token от ЮКассы
COURSE_CHANNEL_ID = os.getenv("COURSE_CHANNEL_ID", "") # ID канала курса (числовой, -100...)

TECHNIQUE_URL = "https://youtu.be/iDxW8sOII98?si=jBROUhrJdAUriJMK"

KRUZHOK_DIAG_PATH = os.path.join(os.path.dirname(__file__), "kruzhok_diagnostic.mp4")

# ─── ОТСЛЕЖИВАНИЕ ОПЛАТ ───────────────────────────────────────────────────────
paid_users: set = set()          # user_id тех, кто оплатил (сессия)

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
        InlineKeyboardButton("A", callback_data=f"{prefix}_a"),
        InlineKeyboardButton("B", callback_data=f"{prefix}_b"),
        InlineKeyboardButton("C", callback_data=f"{prefix}_c"),
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
KRUZHOK_1_PATH = os.path.join(os.path.dirname(__file__), "kruzhok_1.mp4")
KRUZHOK_2_PATH = os.path.join(os.path.dirname(__file__), "kruzhok_2.mp4")


async def delayed_video_note(bot, chat_id: int):
    await asyncio.sleep(3)   # TEST: было 15 * 60
    # 1 — первый кружок
    try:
        with open(KRUZHOK_1_PATH, "rb") as f:
            await asyncio.wait_for(
                bot.send_video_note(chat_id=chat_id, video_note=f),
                timeout=60,
            )
    except Exception as exc:
        logger.warning("Kruzhok 1 failed: %s", exc)
    # 2 — второй кружок
    try:
        with open(KRUZHOK_2_PATH, "rb") as f:
            await asyncio.wait_for(
                bot.send_video_note(chat_id=chat_id, video_note=f),
                timeout=60,
            )
    except Exception as exc:
        logger.warning("Kruzhok 2 failed: %s", exc)
    # 3 — сообщение о курсе с кнопкой
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "✨ *Курс «Основы управления интуицией»*\n\n"
                "За 1 неделю ты освоишь, а за 1 месяц прокачаешь "
                "базовый навык считывания любой информации\n\n"
                "*До курса:*\n"
                "· Чувствуете, что человеку нельзя доверять, но не можете объяснить почему\n"
                "· Соглашаетесь вопреки внутреннему ощущению, а потом жалеете\n"
                "· В разговоре плохо понимаете человека или он вас\n"
                "· Испытываете напряжение, когда нужно быстрое решение в условиях неопределённости\n"
                "· Игнорируете интуицию или принимаете импульсивные решения\n\n"
                "*После курса:*\n"
                "· Считываете людей — эмоции, намерения, скрытые мотивы\n"
                "· Принимаете точные решения когда данных и времени мало\n"
                "· Прогнозируете исходы переговоров, партнёрств, сделок\n"
                "· Доверяете первому ощущению без ошибок\n"
                "· Видите ситуацию на шаг вперёд\n"
                "· Понимаете, как избежать конфликта с близкими\n\n"
                "*Что включено:*\n"
                "— 7 уроков до 20 минут\n"
                "— Практические задания на каждый день\n"
                "— Обратная связь от Марии в телеграме\n"
                "— Сообщество развивающихся людей\n"
                "— Доступ на 1 месяц"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Активировать спец. условия",
                    callback_data="spec_offer"
                ),
            ]]),
        )
    except Exception as exc:
        logger.warning("Course message failed: %s", exc)
    logger.info("Kruzhki + course message sent to chat %s", chat_id)


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
        "Привет 👋\n"
        "Я помощник Марии Альпидовской, эксперта по развитию интуиции\n\n"
        "Ниже тест из 5 вопросов 👇\n"
        "Он поможет определить, насколько включена твоя интуиция прямо сейчас ;)",
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
    context.user_data["current_step"] = "1 · Начал тест (увидел В1)"
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
    context.user_data["current_step"] = "3 · Ответил на В1"
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
                "А — Что-то в поведении или взгляде одного из них\n\n"
                "B — Обычная рабочая встреча\n\n"
                "C — Ничего особенного не замечаю"
            ),
            parse_mode="Markdown",
            reply_markup=abc_kb("q2"),
        )
    return WAIT_Q2


async def answer_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q2", q.data.split("_")[1])
    context.user_data["current_step"] = "4 · Ответил на В2"
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
    context.user_data["current_step"] = "5 · Ответил на В3"
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
                [InlineKeyboardButton("A — Солнечное лето ☀️",  callback_data="q4_a")],
                [InlineKeyboardButton("B — Дождливая осень 🌧", callback_data="q4_b")],
                [InlineKeyboardButton("C — Снежная зима ❄️",    callback_data="q4_c")],
            ]),
        )
    return WAIT_Q4


async def answer_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    add_score(context, "q4", q.data.split("_")[1])
    context.user_data["current_step"] = "6 · Ответил на В4"
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
                "A — Левая. Шум, тревога\n\n"
                "B — Правая. Умею находить тишину внутри\n\n"
                "C — Зависит от ситуации"
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
    context.user_data["current_step"] = "8 · Получил результат ✅"

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
            "Ваш канал интуиции нестабилен.\n\n"
            "Интуиция — это тренируемый навык, который можно прокачать так же, "
            "как бицепс, пресс или ягодицы. Всё дело в регулярной практике."
        )
        tier = f"⚡️ Интуиция нестабильна ({total}/10)"
    else:
        title = "🌱 Сигнал сложно услышать"
        body  = (
            "Ваша интуиция сейчас спит, и к ней сложно пробиться. "
            "Слишком много логики, анализа и внешних ориентиров. "
            "Но не стоит отчаиваться.\n\n"
            "Интуиция — это тренируемый навык, который можно прокачать так же, "
            "как бицепс, пресс или ягодицы. Всё дело в регулярной практике."
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
    LESSON_COVER = os.path.join(os.path.dirname(__file__), "images", "lesson_cover.jpg")
    NEW_LESSON_URL = "https://youtu.be/VH1owF12BLY"
    bot_ref = context.bot
    async def send_youtube():
        try:
            with open(LESSON_COVER, "rb") as cover:
                await bot_ref.send_photo(chat_id=chat_id_for_yt, photo=cover)
        except Exception as exc:
            logger.warning("Lesson cover failed: %s", exc)
        await bot_ref.send_message(
            chat_id=chat_id_for_yt,
            text=(
                "В вводном уроке курса\n"
                "«Основы управления интуицией»\n"
                "Мария рассказывает о том, <b>как работает наш мозг "
                "и что нужно делать, чтобы прокачать интуицию</b>.\n\n"
                f"<b>👇 Смотреть урок</b>\n{NEW_LESSON_URL}\n\n"
                "00:00 — Введение. Что такое управление интуицией\n"
                "00:27 — Как мозг получает и обрабатывает информацию\n"
                "05:00 — Пять органов чувств и шестой канал восприятия\n"
                "09:02 — Что максимально включает интуицию\n"
                "13:25 — Как считать намерение другого человека\n"
                "14:25 — Главное правило тренировки интуиции"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    asyncio.create_task(send_youtube())

    # ─ Запускаем отложенные задачи ────────────────────────────────────────
    chat_id = q.message.chat_id
    asyncio.create_task(delayed_video_note(context.bot, chat_id))

    # Уведомляем администратора
    try:
        await notify_admin(context, user=from_user, test_result=tier)
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)

    logger.info("User %s finished test. Score: %d", from_user.id, total)
    return MENU


# ══════════════════════════════════════════════════════════════════════════════
# СВОБОДНЫЙ ТЕКСТ → УВЕДОМЛЕНИЕ АДМИНИСТРАТОРУ
# ══════════════════════════════════════════════════════════════════════════════
async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Любое текстовое сообщение вне кнопок → уведомление администратору + лог в таблицу."""
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    text = update.message.text
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    tg   = f"@{user.username}" if user.username else "нет username"

    # Определяем, на каком шаге воронки сейчас находится пользователь
    step_label = context.user_data.get("current_step", "неизвестно")

    # Уведомляем администратора
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"💬 *Сообщение от пользователя*\n\n"
                    f"👤 {name}\n"
                    f"📱 {tg}  |  ID: `{user.id}`\n"
                    f"📍 Шаг воронки: {step_label}\n\n"
                    f"✏️ {text}"
                ),
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.warning("Admin free-text notify failed: %s", exc)

    # Логируем в Google Sheets
    asyncio.create_task(log_to_sheet(
        "free_text",
        name=name,
        username=f"@{user.username}" if user.username else "",
        user_id=user.id,
        message=text[:500],
        step=step_label,
    ))


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
# КНОПКА «Активировать спец. условия»
# ══════════════════════════════════════════════════════════════════════════════
async def spec_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "🔥 *Специальные условия для тебя*\n"
        "Стандартная цена курса: 6 990 ₽\n\n"
        "В ближайшие 60 минут цена курса для тебя:\n"
        "→ 10 ₽ \\(тестовая оплата\\)\n\n"
        "После — стоимость вернётся к стандартной 🕐",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Приобрести курс за 10 ₽",
                callback_data="buy_course"
            ),
        ]]),
    )
    # Запускаем таймер: если не оплатит за 60 мин — отправляем диагностику
    asyncio.create_task(delayed_no_payment_reminder(
        context.bot, q.message.chat_id, q.from_user.id
    ))


# ══════════════════════════════════════════════════════════════════════════════
# КНОПКА «Приобрести курс» → согласие + счёт сразу
# ══════════════════════════════════════════════════════════════════════════════
async def buy_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # Показываем согласие + кнопку «Оплатить»
    await q.message.reply_text(
        'Нажимая кнопку "Оплатить", вы соглашаетесь:\n\n'
        '☑️ Я ознакомлен(а) с <a href="https://maria-alpidovskaya.ru/oferta">публичной Офертой</a>\n\n'
        '☑️ Я ознакомлен(а) с <a href="https://maria-alpidovskaya.ru/politika-opd">Политикой обработки персональных данных</a> '
        'и с <a href="https://maria-alpidovskaya.ru/soglasie-opd">Согласием на обработку персональных данных</a>\n\n'
        '☑️ Я даю согласие на получение бесплатных гайдов, памяток, чек-листов, а также иных материалов '
        'информационного и рекламного характера, в том числе посредством sms-уведомления.',
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 Оплатить", callback_data="pay_now"),
        ]]),
    )


async def pay_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await context.bot.send_invoice(
            chat_id=q.message.chat_id,
            title="Курс «Основы управления интуицией»",
            description="Доступ к курсу на 1 месяц: 7 уроков, практические задания, обратная связь от Марии",
            payload="course_intuition_3990",
            provider_token=YOOKASSA_TOKEN,
            currency="RUB",
            prices=[LabeledPrice("Курс «Основы управления интуицией»", 1000)],  # 10 ₽ (в копейках)
            need_name=True,
            need_email=True,
            need_phone_number=True,
        )
    except Exception as e:
        print(f"[PAY_NOW ERROR] send_invoice failed: {type(e).__name__}: {e}", flush=True)
        logger.error("send_invoice failed: %s", e)
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text="Не удалось открыть оплату. Попробуйте ещё раз или напишите нам.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PRE-CHECKOUT + УСПЕШНАЯ ОПЛАТА
# ══════════════════════════════════════════════════════════════════════════════
async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    paid_users.add(user.id)

    purchase_date = datetime.now().strftime("%d.%m.%Y")
    expiry_date   = (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y")

    # 1 — Даём доступ к каналу курса
    channel_link = "https://t.me/+VNnNxLOM3BE5NTEy"
    if COURSE_CHANNEL_ID:
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=int(COURSE_CHANNEL_ID),
                member_limit=1,
            )
            channel_link = invite.invite_link
        except Exception as exc:
            logger.warning("Channel invite failed: %s", exc)

    await update.message.reply_text(
        f"✅ Оплата прошла успешно!\n\n"
        f"Вот твоя персональная ссылка для входа в курс:\n{channel_link}\n\n"
        f"Доступ действует до {expiry_date}. Добро пожаловать! 🎉"
    )

    # 2 — Логируем покупку в таблицу
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    tg   = f"@{user.username}" if user.username else ""
    asyncio.create_task(log_to_sheet(
        "purchase",
        name=name,
        username=tg,
        user_id=user.id,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        amount="3990",
    ))

    # 3 — Уведомляем администратора
    if ADMIN_CHAT_ID:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "💰 *Новая оплата курса*\n\n"
                f"👤 {name}\n"
                f"📱 {tg}  |  ID: `{user.id}`\n"
                f"💵 Сумма: 3 990 ₽\n"
                f"📅 Доступ до: {expiry_date}"
            ),
            parse_mode="Markdown",
        )

    # 4 — Через 29 дней напоминание о продлении
    asyncio.create_task(delayed_renewal_reminder(context.bot, update.message.chat_id, user.id))


# ══════════════════════════════════════════════════════════════════════════════
# НАПОМИНАНИЕ О ПРОДЛЕНИИ (через 29 дней)
# ══════════════════════════════════════════════════════════════════════════════
async def delayed_renewal_reminder(bot, chat_id: int, user_id: int):
    await asyncio.sleep(3 * 60)  # TEST: было 29 * 24 * 60 * 60
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⏰ Завтра заканчивается доступ к курсу «Основы управления интуицией».\n\n"
                "У вас есть возможность продлить доступ ещё на один месяц всего за 990 ₽."
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Продлить курс за 990 ₽", callback_data="renew_course"),
            ]]),
        )
    except Exception as exc:
        logger.warning("Renewal reminder failed: %s", exc)


async def renew_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await context.bot.send_invoice(
        chat_id=q.message.chat_id,
        title="Продление курса «Основы управления интуицией»",
        description="Продление доступа к курсу на 1 месяц",
        payload="course_renewal_990",
        provider_token=YOOKASSA_TOKEN,
        currency="RUB",
        prices=[LabeledPrice("Продление курса", 1000)],  # TEST: 10 ₽, боевое: 99000
        need_name=True,
        need_email=True,
        need_phone_number=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# НАПОМИНАНИЕ ДЛЯ НЕ ОПЛАТИВШИХ (через 60 минут)
# ══════════════════════════════════════════════════════════════════════════════
async def delayed_no_payment_reminder(bot, chat_id: int, user_id: int):
    await asyncio.sleep(2 * 60)  # TEST: было 60 * 60
    if user_id in paid_users:
        return  # уже оплатил — не отправляем
    # Кружок
    try:
        with open(KRUZHOK_DIAG_PATH, "rb") as f:
            await bot.send_video_note(chat_id=chat_id, video_note=f)
    except Exception as exc:
        logger.warning("Diagnostic kruzhok failed: %s", exc)
    # Сообщение с кнопкой
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "Беспокоит нерешённый вопрос в личной или деловой сфере?\n\n"
                "Приглашаю тебя на *бесплатную диагностику*, где за 30 минут ты получишь:\n\n"
                "· ясный ответ на свой запрос\n"
                "· индивидуальные рекомендации: как именно тебе стоит развивать интуицию, "
                "чтобы больше не прибегать к советникам"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Записаться на диагностику",
                    url="https://t.me/svami_assistent?text=%D0%97%D0%B4%D1%80%D0%B0%D0%B2%D1%81%D1%82%D0%B2%D1%83%D0%B9%D1%82%D0%B5%21%20%D0%A5%D0%BE%D1%87%D1%83%20%D0%B7%D0%B0%D0%BF%D0%B8%D1%81%D0%B0%D1%82%D1%8C%D1%81%D1%8F%20%D0%BA%20%D0%9C%D0%B0%D1%80%D0%B8%D0%B8%20%D0%BD%D0%B0%20%D0%B1%D0%B5%D1%81%D0%BF%D0%BB%D0%B0%D1%82%D0%BD%D1%83%D1%8E%20%D0%B4%D0%B8%D0%B0%D0%B3%D0%BD%D0%BE%D1%81%D1%82%D0%B8%D0%BA%D1%83"
                ),
            ]]),
        )
    except Exception as exc:
        logger.warning("No-payment diagnostic message failed: %s", exc)


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
    # Кнопки вне ConversationHandler (приходят после теста)
    app.add_handler(CallbackQueryHandler(spec_offer_callback,  pattern="^spec_offer$"))
    app.add_handler(CallbackQueryHandler(buy_course_callback,  pattern="^buy_course$"))
    app.add_handler(CallbackQueryHandler(pay_now_callback,     pattern="^pay_now$"))
    app.add_handler(CallbackQueryHandler(renew_course_callback, pattern="^renew_course$"))
    # ЮКасса: подтверждение и успешная оплата
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    # Свободный текст вне кнопок → уведомление администратору
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    logger.info("Бот запущен ✓")
    app.run_polling()


if __name__ == "__main__":
    main()
