import os
import sqlite3
import logging
import html
import time
from datetime import datetime

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# НАСТРОЙКИ
# ============================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8999035301"))

DB = "rewet_host.db"

SUPPORT_USERNAME = "@d3v_menedsvoyak"

# Антиспам в группах
GROUP_COOLDOWN = 5

# Последнее время ответа пользователей
group_cooldowns = {}

# Username самого бота
BOT_USERNAME = ""


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ============================================================
# ВОПРОСЫ АНКЕТЫ
# ============================================================

QUESTIONS = [
    ("👤 Имя / никнейм", "name"),
    ("🎂 Возраст", "age"),
    ("💻 Опыт работы с игровыми серверами/хостингом", "experience"),
    ("🛠️ Навыки (Pawn, плагины, настройка и т.д.)", "skills"),
    ("💬 Готовы отвечать пользователям и помогать с ошибками?", "support"),
    ("⏰ Сколько времени в день готовы уделять проекту?", "time"),
    ("🤝 Почему хотите попасть в команду REWET HOST?", "why"),
    ("⭐ Чем будете полезны проекту?", "useful"),
    ("📋 Опыт в других проектах/командах", "projects"),
    ("📝 Расскажите немного о себе", "about"),
]

# ============================================================
# БАЗА ДАННЫХ
# ============================================================

def conn():
    c = sqlite3.connect(DB)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_seen TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            status TEXT DEFAULT 'pending',
            data TEXT,
            created_at TEXT
        )
    """)

    c.commit()

    return c


def register_user(user):
    if not user:
        return

    c = conn()

    c.execute(
        """
        INSERT OR IGNORE INTO users
        (user_id, username, first_seen)
        VALUES (?, ?, ?)
        """,
        (
            user.id,
            user.username or "",
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    c.execute(
        """
        UPDATE users
        SET username=?
        WHERE user_id=?
        """,
        (
            user.username or "",
            user.id,
        ),
    )

    c.commit()
    c.close()


def get_pending_application(user_id):
    c = conn()

    row = c.execute(
        """
        SELECT id, data, created_at
        FROM applications
        WHERE user_id=?
        AND status='pending'
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    c.close()

    return row


def get_application(app_id):
    c = conn()

    row = c.execute(
        """
        SELECT id, user_id, username, status, data, created_at
        FROM applications
        WHERE id=?
        """,
        (app_id,),
    ).fetchone()

    c.close()

    return row


# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📝 Подать заявку",
                callback_data="apply"
            )
        ],
        [
            InlineKeyboardButton(
                "👤 Профиль",
                callback_data="profile"
            ),
            InlineKeyboardButton(
                "📋 Моя заявка",
                callback_data="my"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 О проекте",
                callback_data="about"
            ),
            InlineKeyboardButton(
                "💬 Поддержка",
                callback_data="support"
            )
        ],
    ])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📋 Заявки",
                callback_data="admin_apps"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Статистика",
                callback_data="admin_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Пользователи",
                callback_data="admin_users"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Главное меню",
                callback_data="home"
            )
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 Главное меню",
                callback_data="home"
            )
        ]
    ])


# ============================================================
# КОМАНДЫ ПОМОЩИ
# ============================================================

async def help_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    register_user(update.effective_user)

    text = (
        "🔥 <b>REWET HOST — ПОМОЩЬ</b>\n\n"

        "🤖 Этот бот помогает участникам проекта "
        "REWET HOST.\n\n"

        "📌 <b>Основные команды:</b>\n"
        "/start — главное меню\n"
        "/help — помощь\n"
        "/commands — список команд\n"
        "/support — поддержка\n"
        "/errors — помощь с типовыми ошибками\n"
        "/chat — как обратиться к боту\n"
        "/cancel — отменить заполнение заявки\n\n"

        "👥 <b>В группе</b>\n"
        "Упомяните бота через @username или "
        "ответьте на сообщение бота.\n\n"

        "🛠️ Можно спрашивать про:\n"
        "• Pawn\n"
        "• SA-MP\n"
        "• плагины\n"
        "• ошибки компиляции\n"
        "• конфигурацию сервера\n"
        "• запуск сервера"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


async def commands_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    await help_command(update, ctx)


async def support_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    register_user(update.effective_user)

    await update.message.reply_text(
        "💬 <b>ПОДДЕРЖКА REWET HOST</b>\n\n"

        "Если у вас проблема с проектом, "
        "сервером или ботом — обратитесь к администратору.\n\n"

        f"👨‍💻 Администратор: {SUPPORT_USERNAME}\n\n"

        "💡 При обращении желательно отправить:\n"
        "• текст ошибки;\n"
        "• лог;\n"
        "• скриншот;\n"
        "• что вы делали перед появлением ошибки.",

        parse_mode="HTML",
    )


async def errors_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    register_user(update.effective_user)

    await update.message.reply_text(
        "🛠️ <b>ПОМОЩЬ С ОШИБКАМИ</b>\n\n"

        "🔴 <b>error 017: undefined symbol</b>\n"
        "Переменная, функция или символ не объявлены.\n"
        "Проверьте название и наличие нужного include.\n\n"

        "🔴 <b>error 017: undefined symbol \"CMD:...\"</b>\n"
        "Проверьте подключение Pawn.CMD или "
        "использование правильного синтаксиса команды.\n\n"

        "🔴 <b>fatal error 100: cannot read from file</b>\n"
        "Компилятор не может найти include-файл.\n"
        "Проверьте папку pawno/include.\n\n"

        "🔴 <b>error 021: symbol already defined</b>\n"
        "Одинаковый символ объявлен несколько раз.\n"
        "Проверьте дублирующиеся функции, переменные или defines.\n\n"

        "🔴 <b>Сервер не запускается</b>\n"
        "Проверьте server_log.txt, plugins, includes "
        "и конфигурацию server.cfg.\n\n"

        "📩 Если не знаете, как исправить ошибку — "
        "отправьте её полностью в чат и вызовите бота.",

        parse_mode="HTML",
    )


async def chat_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "💬 <b>КАК ОБЩАТЬСЯ С БОТОМ</b>\n\n"

        "В группе напишите:\n"
        "<code>/help</code>\n\n"

        "или упомяните меня:\n"
        "<code>@имя_бота помоги с error 017</code>\n\n"

        "Также можно ответить на сообщение бота.\n\n"

        "⚠️ ИИ пока не подключён.\n"
        "Сейчас работают готовые подсказки и "
        "автоматическое распознавание распространённых ошибок.",

        parse_mode="HTML",
    )


# ============================================================
# ПОИСК ОШИБОК
# ============================================================

def detect_error(text):
    if not text:
        return None

    lower = text.lower()

    if "error 017" in lower:
        return (
            "🔴 <b>Error 017 — undefined symbol</b>\n\n"
            "Скорее всего, компилятор не знает "
            "указанный символ.\n\n"
            "Проверь:\n"
            "• подключён ли нужный include;\n"
            "• правильно ли написано имя;\n"
            "• объявлена ли переменная/функция."
        )

    if "fatal error 100" in lower:
        return (
            "🔴 <b>Fatal Error 100</b>\n\n"
            "Компилятор не может найти include-файл.\n\n"
            "Проверь папку:\n"
            "<code>pawno/include</code>\n\n"
            "И строку <code>#include</code>."
        )

    if "error 021" in lower:
        return (
            "🔴 <b>Error 021 — symbol already defined</b>\n\n"
            "Один и тот же символ объявлен несколько раз.\n\n"
            "Проверь дублирующиеся:\n"
            "• функции;\n"
            "• переменные;\n"
            "• #define;\n"
            "• enum."
        )

    if "error 025" in lower:
        return (
            "🔴 <b>Error 025 — function heading differs</b>\n\n"
            "Сигнатура функции отличается от объявления.\n\n"
            "Проверь количество и типы параметров."
        )

    if "undefined symbol" in lower:
        return (
            "🔴 <b>Undefined symbol</b>\n\n"
            "Неизвестный для компилятора символ.\n"
            "Проверь объявление переменной/функции "
            "и подключение нужных include."
        )

    if "cannot read from file" in lower:
        return (
            "🔴 <b>Cannot read from file</b>\n\n"
            "Не найден include-файл.\n\n"
            "Проверь наличие файла в:\n"
            "<code>pawno/include</code>"
        )

    if "server.exe" in lower or "crashdetect" in lower:
        return (
            "💥 <b>Возможная проблема запуска/краша SA-MP</b>\n\n"
            "Отправь полный текст server_log.txt "
            "или crashdetect.log.\n\n"
            "По одному названию файла определить "
            "точную причину нельзя."
        )

    return None


# ============================================================
# ГРУППОВОЙ РЕЖИМ
# ============================================================

def is_group(update):
    if not update.effective_chat:
        return False

    return update.effective_chat.type in (
        "group",
        "supergroup",
    )


def is_bot_mentioned(message):
    if not message:
        return False

    text = message.text or ""

    if not BOT_USERNAME:
        return False

    username = BOT_USERNAME.lower()

    return f"@{username}" in text.lower()


def is_reply_to_bot(message):
    if not message:
        return False

    reply = message.reply_to_message

    if not reply:
        return False

    if not reply.from_user:
        return False

    return reply.from_user.is_bot and (
        reply.from_user.username or ""
    ).lower() == BOT_USERNAME.lower()


def check_group_cooldown(user_id):
    now = time.time()

    previous = group_cooldowns.get(user_id, 0)

    if now - previous < GROUP_COOLDOWN:
        return False

    group_cooldowns[user_id] = now

    # Очистка старых записей
    if len(group_cooldowns) > 1000:
        old_keys = [
            uid
            for uid, timestamp in group_cooldowns.items()
            if now - timestamp > 60
        ]

        for uid in old_keys:
            group_cooldowns.pop(uid, None)

    return True


async def group_message_handler(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    if not is_group(update):
        return

    message = update.message
    user = update.effective_user

    register_user(user)

    # Бот отвечает только на упоминание
    # или ответ на сообщение бота.
    if not is_bot_mentioned(message) and not is_reply_to_bot(message):
        return

    if not check_group_cooldown(user.id):
        await message.reply_text(
            "⏳ Не так быстро. Попробуйте через несколько секунд."
        )
        return

    original_text = message.text or ""

    # Убираем @username бота
    text = original_text

    if BOT_USERNAME:
        text = text.replace(
            f"@{BOT_USERNAME}",
            ""
        )

        text = text.replace(
            f"@{BOT_USERNAME.lower()}",
            ""
        )

    text = text.strip()

    if not text:
        await message.reply_text(
            "👋 Я здесь!\n\n"
            "Напишите, с чем помочь.\n\n"
            "Например:\n"
            "• error 017\n"
            "• не запускается сервер\n"
            "• как подключить include\n\n"
            "📚 /help — список возможностей"
        )
        return

    error_answer = detect_error(text)

    if error_answer:
        await message.reply_text(
            error_answer,
            parse_mode="HTML",
        )
        return

    lower = text.lower()

    if (
        "привет" in lower
        or "здравствуй" in lower
        or "хай" in lower
    ):
        await message.reply_text(
            "👋 Привет!\n"
            "Я помощник REWET HOST.\n\n"
            "Могу подсказать по Pawn, SA-MP, "
            "ошибкам и настройке сервера.\n\n"
            "🛠️ Отправь свою проблему."
        )
        return

    if "помощ" in lower or "что умеешь" in lower:
        await message.reply_text(
            "🛠️ <b>Я могу помочь с:</b>\n\n"
            "• Pawn\n"
            "• SA-MP\n"
            "• plugins\n"
            "• includes\n"
            "• ошибками компиляции\n"
            "• server.cfg\n"
            "• запуском сервера\n\n"
            "📚 Команды: /help"
            ,
            parse_mode="HTML",
        )
        return

    await message.reply_text(
        "🤔 Я пока не смог определить проблему.\n\n"
        "Отправьте <b>полный текст ошибки</b>, "
        "лог или опишите, что произошло.\n\n"
        "📚 /errors — список частых ошибок\n"
        "💬 /support — поддержка",
        parse_mode="HTML",
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    register_user(update.effective_user)

    ctx.user_data.clear()

    text = (
        "🔥 <b>REWET HOST</b>\n\n"
        "Добро пожаловать в официальный бот проекта!\n\n"
        "🚀 Игровой хостинг нового поколения\n"
        "⚡ Быстрый запуск серверов\n"
        "🛡️ Надёжность и стабильность\n"
        "🤝 Развивающаяся команда\n\n"
        "Выберите нужный раздел:"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


# ============================================================
# /ADMIN
# ============================================================

async def admin_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Доступ запрещён."
        )
        return

    await update.message.reply_text(
        "👨‍💼 <b>АДМИН-ПАНЕЛЬ REWET HOST</b>\n\n"
        "Выберите нужный раздел:",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================

async def menu_callback(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query

    await q.answer()

    register_user(q.from_user)

    if q.data == "home":

        await q.message.edit_text(
            "🔥 <b>REWET HOST</b>\n\n"
            "Главное меню:",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    elif q.data == "about":

        await q.message.edit_text(
            "🚀 <b>REWET HOST</b>\n\n"

            "Добро пожаловать в REWET HOST — "
            "игровой хостинг для владельцев серверов "
            "и разработчиков.\n\n"

            "⚡ <b>Быстрый запуск</b>\n"
            "Запускайте игровые проекты быстро и удобно.\n\n"

            "🛡️ <b>Надёжность</b>\n"
            "Мы стремимся обеспечить стабильную работу "
            "ваших игровых серверов.\n\n"

            "💻 <b>Удобство</b>\n"
            "Развиваем удобную инфраструктуру и инструменты "
            "для управления проектами.\n\n"

            "🤝 <b>Команда</b>\n"
            "REWET HOST развивается вместе с участниками "
            "нашего проекта.\n\n"

            "🔥 <b>Наша цель</b>\n"
            "Создать удобный, доступный и современный "
            "игровой хостинг.\n\n"

            f"👨‍💻 <b>Администратор:</b> {SUPPORT_USERNAME}",

            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )

    elif q.data == "support":

        await q.message.edit_text(
            "💬 <b>ПОДДЕРЖКА REWET HOST</b>\n\n"

            "Возник вопрос или проблема?\n"
            "Обратитесь к администратору проекта.\n\n"

            "👨‍💻 <b>Администратор</b>\n"
            f"{SUPPORT_USERNAME}\n\n"

            "📩 По вопросам сотрудничества, заявок, "
            "ошибок и работы проекта обращайтесь "
            "к администратору.\n\n"

            "💡 <b>Совет:</b>\n"
            "При обращении подробно опишите проблему "
            "и приложите скриншот, если это необходимо.",

            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )

    elif q.data == "profile":

        c = conn()

        user = c.execute(
            """
            SELECT first_seen
            FROM users
            WHERE user_id=?
            """,
            (q.from_user.id,),
        ).fetchone()

        applications = c.execute(
            """
            SELECT COUNT(*)
            FROM applications
            WHERE user_id=?
            """,
            (q.from_user.id,),
        ).fetchone()[0]

        accepted = c.execute(
            """
            SELECT COUNT(*)
            FROM applications
            WHERE user_id=?
            AND status='accepted'
            """,
            (q.from_user.id,),
        ).fetchone()[0]

        c.close()

        username = (
            f"@{q.from_user.username}"
            if q.from_user.username
            else "не указан"
        )

        first_seen = user[0] if user else "неизвестно"

        await q.message.edit_text(
            "👤 <b>ВАШ ПРОФИЛЬ</b>\n\n"

            f"🆔 ID: <code>{q.from_user.id}</code>\n"
            f"🔗 Username: {html.escape(username)}\n"
            f"📅 Регистрация: {first_seen}\n\n"

            f"📨 Заявок отправлено: <b>{applications}</b>\n"
            f"🟢 Одобрено: <b>{accepted}</b>",

            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )

    elif q.data == "my":

        row = get_pending_application(q.from_user.id)

        if row:

            app_id, data, created_at = row

            await q.message.edit_text(
                "📋 <b>МОЯ ЗАЯВКА</b>\n\n"

                f"🆔 Номер: <b>#{app_id}</b>\n"
                f"📅 Создана: {created_at}\n"
                "⏳ Статус: <b>На рассмотрении</b>\n\n"

                "Администрация сообщит вам о решении.",

                parse_mode="HTML",
                reply_markup=back_keyboard(),
            )

        else:

            await q.message.edit_text(
                "📋 <b>МОЯ ЗАЯВКА</b>\n\n"
                "Активной заявки нет.\n\n"
                "Вы можете подать новую заявку "
                "через главное меню.",

                parse_mode="HTML",
                reply_markup=back_keyboard(),
            )

    elif q.data == "apply":

        if get_pending_application(q.from_user.id):

            await q.message.edit_text(
                "⚠️ <b>У вас уже есть заявка.</b>\n\n"
                "Дождитесь решения администрации.",

                parse_mode="HTML",
                reply_markup=back_keyboard(),
            )

            return

        ctx.user_data.clear()

        ctx.user_data["answers"] = []
        ctx.user_data["step"] = 0

        await q.message.edit_text(
            "📝 <b>ЗАПОЛНЕНИЕ ЗАЯВКИ</b>\n\n"
            "Ответьте на вопросы анкеты.\n\n"
            f"<b>Вопрос 1 из {len(QUESTIONS)}</b>\n"
            f"{QUESTIONS[0][0]}\n\n"
            "❌ Для отмены используйте /cancel",

            parse_mode="HTML",
        )


# ============================================================
# ТЕКСТ АНКЕТЫ
# ============================================================

async def text_handler(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    # В группах работает отдельный обработчик
    if is_group(update):
        return

    if "step" not in ctx.user_data:
        return

    step = ctx.user_data["step"]

    if step == "confirm":
        return

    answer = update.message.text.strip()

    if not answer:
        await update.message.reply_text(
            "⚠️ Ответ не может быть пустым."
        )
        return

    if len(answer) > 1500:

        await update.message.reply_text(
            "⚠️ Ответ слишком длинный.\n"
            "Максимум — 1500 символов."
        )

        return

    ctx.user_data["answers"].append(answer)

    step += 1

    if step < len(QUESTIONS):

        ctx.user_data["step"] = step

        await update.message.reply_text(
            f"➡️ <b>Вопрос {step + 1} из {len(QUESTIONS)}</b>\n\n"
            f"{QUESTIONS[step][0]}",

            parse_mode="HTML",
        )

        return

    ctx.user_data["step"] = "confirm"

    answers = ctx.user_data["answers"]

    text = "📋 <b>ПРОВЕРЬТЕ АНКЕТУ</b>\n\n"

    for (label, _), value in zip(QUESTIONS, answers):

        text += (
            f"<b>{html.escape(label)}</b>\n"
            f"{html.escape(value)}\n\n"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Отправить",
                callback_data="send_application"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отменить",
                callback_data="cancel_application"
            )
        ],
    ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ============================================================
# ОТПРАВКА ЗАЯВКИ
# ============================================================

async def application_callback(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query

    await q.answer()

    if q.data == "cancel_application":

        ctx.user_data.clear()

        await q.edit_message_text(
            "❌ <b>Заявка отменена.</b>\n\n"
            "Вы можете начать заполнение заново.",

            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )

        return

    if ctx.user_data.get("step") != "confirm":

        await q.message.reply_text(
            "⚠️ Сессия заполнения устарела.\n"
            "Используйте /start и начните заново."
        )

        return

    answers = ctx.user_data["answers"]

    c = conn()

    cur = c.execute(
        """
        INSERT INTO applications
        (user_id, username, status, data, created_at)
        VALUES (?, ?, 'pending', ?, ?)
        """,
        (
            q.from_user.id,
            q.from_user.username or "",
            repr(answers),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    app_id = cur.lastrowid

    c.commit()
    c.close()

    msg = (
        f"📨 <b>НОВАЯ ЗАЯВКА #{app_id}</b>\n\n"
        f"👤 ID: <code>{q.from_user.id}</code>\n"
    )

    if q.from_user.username:
        msg += (
            f"🔗 @{html.escape(q.from_user.username)}\n"
        )

    msg += "\n"

    for (label, _), value in zip(QUESTIONS, answers):

        msg += (
            f"<b>{html.escape(label)}</b>\n"
            f"{html.escape(value)}\n\n"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Принять",
                callback_data=f"accept:{app_id}"
            ),
            InlineKeyboardButton(
                "🔴 Отклонить",
                callback_data=f"reject:{app_id}"
            ),
        ]
    ])

    try:

        await ctx.bot.send_message(
            ADMIN_ID,
            msg,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception:

        logging.exception(
            "Не удалось отправить заявку админу"
        )

    ctx.user_data.clear()

    await q.edit_message_text(
        f"✅ <b>Заявка #{app_id} отправлена!</b>\n\n"
        "⏳ Администрация рассмотрит её "
        "и сообщит вам о решении.",

        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


# ============================================================
# ПРИНЯТЬ / ОТКЛОНИТЬ
# ============================================================

async def admin_action(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query

    if q.from_user.id != ADMIN_ID:

        await q.answer(
            "⛔ Доступ запрещён.",
            show_alert=True,
        )

        return

    await q.answer()

    action, raw_id = q.data.split(":")

    app_id = int(raw_id)

    row = get_application(app_id)

    if not row:

        await q.message.reply_text(
            "❌ Заявка не найдена."
        )

        return

    user_id = row[1]
    status = row[3]

    if status != "pending":

        await q.message.reply_text(
            "⚠️ Эта заявка уже обработана."
        )

        return

    new_status = (
        "accepted"
        if action == "accept"
        else "rejected"
    )

    c = conn()

    c.execute(
        """
        UPDATE applications
        SET status=?
        WHERE id=?
        """,
        (
            new_status,
            app_id,
        ),
    )

    c.commit()
    c.close()

    if new_status == "accepted":

        user_text = (
            f"🎉 <b>Заявка #{app_id} одобрена!</b>\n\n"
            "🔥 Поздравляем!\n"
            "Вы приняты в команду <b>REWET HOST</b>.\n\n"
            f"💬 Связь с администрацией: {SUPPORT_USERNAME}"
        )

        result = (
            f"🟢 <b>Заявка #{app_id} принята.</b>"
        )

        admin_notice = (
            f"✅ <b>Заявка #{app_id} принята</b>\n\n"
            f"👤 Пользователь ID: <code>{user_id}</code>\n"
            "🎉 Пользователь уведомлён."
        )

    else:

        user_text = (
            f"❌ <b>Заявка #{app_id} отклонена.</b>\n\n"
            "Спасибо за участие в отборе.\n"
            "Вы можете попробовать подать заявку снова "
            "в будущем."
        )

        result = (
            f"🔴 <b>Заявка #{app_id} отклонена.</b>"
        )

        admin_notice = (
            f"🔴 <b>Заявка #{app_id} отклонена</b>\n\n"
            f"👤 Пользователь ID: <code>{user_id}</code>\n"
            "📩 Пользователь уведомлён."
        )

    try:

        await ctx.bot.send_message(
            user_id,
            user_text,
            parse_mode="HTML",
        )

    except Exception:

        logging.exception(
            "Не удалось уведомить пользователя"
        )

    try:

        await q.edit_message_reply_markup(
            reply_markup=None
        )

    except Exception:
        pass

    await q.message.reply_text(
        result,
        parse_mode="HTML",
    )

    try:

        await ctx.bot.send_message(
            ADMIN_ID,
            admin_notice,
            parse_mode="HTML",
        )

    except Exception:

        logging.exception(
            "Не удалось отправить уведомление админу"
        )


# ============================================================
# СТАТИСТИКА
# ============================================================

async def statistics(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id != ADMIN_ID:
        return

    c = conn()

    users = c.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total = c.execute(
        "SELECT COUNT(*) FROM applications"
    ).fetchone()[0]

    pending = c.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE status='pending'
        """
    ).fetchone()[0]

    accepted = c.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE status='accepted'
        """
    ).fetchone()[0]

    rejected = c.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE status='rejected'
        """
    ).fetchone()[0]

    c.close()

    await update.message.reply_text(
        "📊 <b>REWET HOST — СТАТИСТИКА</b>\n\n"

        f"👥 Пользователей: <b>{users}</b>\n"
        f"📨 Всего заявок: <b>{total}</b>\n"
        f"⏳ На рассмотрении: <b>{pending}</b>\n"
        f"🟢 Принято: <b>{accepted}</b>\n"
        f"🔴 Отклонено: <b>{rejected}</b>",

        parse_mode="HTML",
    )


# ============================================================
# СПИСОК ЗАЯВОК
# ============================================================

async def applications_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id != ADMIN_ID:
        return

    c = conn()

    rows = c.execute(
        """
        SELECT id, user_id, username, status, created_at
        FROM applications
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    c.close()

    if not rows:

        await update.message.reply_text(
            "📋 Заявок пока нет."
        )

        return

    text = "📋 <b>ПОСЛЕДНИЕ ЗАЯВКИ</b>\n\n"

    for app_id, user_id, username, status, created_at in rows:

        if status == "pending":
            icon = "⏳"
            status_name = "На рассмотрении"

        elif status == "accepted":
            icon = "🟢"
            status_name = "Принята"

        else:
            icon = "🔴"
            status_name = "Отклонена"

        text += (
            f"{icon} <b>#{app_id}</b>\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"📌 {status_name}\n"
            f"📅 {created_at}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# АДМИН-КНОПКИ
# ============================================================

async def admin_callback(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query

    if q.from_user.id != ADMIN_ID:

        await q.answer(
            "⛔ Доступ запрещён.",
            show_alert=True,
        )

        return

    await q.answer()

    if q.data == "admin_stats":

        c = conn()

        users = c.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        total = c.execute(
            "SELECT COUNT(*) FROM applications"
        ).fetchone()[0]

        pending = c.execute(
            "SELECT COUNT(*) FROM applications WHERE status='pending'"
        ).fetchone()[0]

        accepted = c.execute(
            "SELECT COUNT(*) FROM applications WHERE status='accepted'"
        ).fetchone()[0]

        rejected = c.execute(
            "SELECT COUNT(*) FROM applications WHERE status='rejected'"
        ).fetchone()[0]

        c.close()

        await q.message.edit_text(
            "📊 <b>СТАТИСТИКА REWET HOST</b>\n\n"

            f"👥 Пользователей: <b>{users}</b>\n\n"
            f"📨 Всего заявок: <b>{total}</b>\n"
            f"⏳ На рассмотрении: <b>{pending}</b>\n"
            f"🟢 Принято: <b>{accepted}</b>\n"
            f"🔴 Отклонено: <b>{rejected}</b>",

            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="admin_back"
                    )
                ]
            ]),
        )

    elif q.data == "admin_users":

        c = conn()

        users = c.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        today = datetime.now().strftime("%Y-%m-%d")

        new_today = c.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE first_seen LIKE ?
            """,
            (today + "%",),
        ).fetchone()[0]

        c.close()

        await q.message.edit_text(
            "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n"

            f"👤 Всего: <b>{users}</b>\n"
            f"🆕 Сегодня: <b>{new_today}</b>",

            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="admin_back"
                    )
                ]
            ]),
        )

    elif q.data == "admin_apps":

        c = conn()

        rows = c.execute(
            """
            SELECT id, user_id, username, status, created_at
            FROM applications
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

        c.close()

        if not rows:

            text = "📋 <b>Заявок пока нет.</b>"

        else:

            text = "📋 <b>ПОСЛЕДНИЕ ЗАЯВКИ</b>\n\n"

            for app_id, user_id, username, status, created_at in rows:

                if status == "pending":
                    icon = "⏳"
                    status_name = "На рассмотрении"

                elif status == "accepted":
                    icon = "🟢"
                    status_name = "Принята"

                else:
                    icon = "🔴"
                    status_name = "Отклонена"

                text += (
                    f"{icon} <b>#{app_id}</b>\n"
                    f"👤 ID: <code>{user_id}</code>\n"
                    f"📌 {status_name}\n"
                    f"📅 {created_at}\n\n"
                )

        await q.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="admin_back"
                    )
                ]
            ]),
        )

    elif q.data == "admin_back":

        await q.message.edit_text(
            "👨‍💼 <b>АДМИН-ПАНЕЛЬ REWET HOST</b>\n\n"
            "Выберите нужный раздел:",

            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )


# ============================================================
# /CANCEL
# ============================================================

async def cancel_command(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):
    ctx.user_data.clear()

    await update.message.reply_text(
        "❌ <b>Текущая анкета сброшена.</b>\n\n"
        "Используйте /start, чтобы открыть меню.",

        parse_mode="HTML",
    )


# ============================================================
# ЗАПУСК
# ============================================================

async def post_init(application):
    global BOT_USERNAME

    try:
        me = await application.bot.get_me()

        BOT_USERNAME = me.username or ""

        logging.info(
            "Бот: @%s",
            BOT_USERNAME
        )

    except Exception:

        logging.exception(
            "Не удалось получить username бота"
        )


def main():

    if not TOKEN:

        raise SystemExit(
            "BOT_TOKEN не указан в переменных окружения Render"
        )

    conn().close()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # ========================================================
    # КОМАНДЫ
    # ========================================================

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin_command)
    )

    app.add_handler(
        CommandHandler("stats", statistics)
    )

    app.add_handler(
        CommandHandler("applications", applications_command)
    )

    app.add_handler(
        CommandHandler("cancel", cancel_command)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("commands", commands_command)
    )

    app.add_handler(
        CommandHandler("support", support_command)
    )

    app.add_handler(
        CommandHandler("errors", errors_command)
    )

    app.add_handler(
        CommandHandler("chat", chat_command)
    )

    # ========================================================
    # ПРИНЯТЬ / ОТКЛОНИТЬ
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            admin_action,
            pattern=r"^(accept|reject):\d+$"
        )
    )

    # ========================================================
    # ЗАЯВКА
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            application_callback,
            pattern=r"^(send_application|cancel_application)$"
        )
    )

    # ========================================================
    # АДМИН-ПАНЕЛЬ
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^(admin_apps|admin_stats|admin_users|admin_back)$"
        )
    )

    # ========================================================
    # ГЛАВНОЕ МЕНЮ
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern=r"^(home|apply|my|profile|about|support)$"
        )
    )

    # ========================================================
    # ГРУППОВОЙ ПОМОЩНИК
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & (
                filters.Entity("mention")
                | filters.REPLY
            ),
            group_message_handler,
        )
    )

    # ========================================================
    # ОТВЕТЫ АНКЕТЫ
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    logging.info(
        "🔥 REWET HOST BOT 5.0 запущен"
    )

    app.run_polling()


if __name__ == "__main__":
    main()
