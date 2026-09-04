import os
import re
import sqlite3
import logging
import html
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

# =========================================================
# НАСТРОЙКИ
# =========================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8999035301"))

DB = "rewet_host.db"
SUPPORT_USERNAME = "@d3v_menedsvoyak"

GROUP_COOLDOWN = 5

BOT_USERNAME = ""
group_cooldowns = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# ВОПРОСЫ ЗАЯВКИ
# =========================================================

APPLICATION_QUESTIONS = [
    "👤 Имя / никнейм",
    "🎂 Возраст",
    "💻 Опыт работы с игровыми серверами/хостингом",
    "🛠️ Навыки (Pawn, плагины, настройка и т.д.)",
    "💬 Готовы отвечать пользователям и помогать с ошибками?",
    "⏰ Сколько времени в день готовы уделять проекту?",
    "🤝 Почему хотите попасть в команду REWET HOST?",
    "⭐ Чем будете полезны проекту?",
    "📋 Опыт в других проектах/командах",
    "📝 Расскажите немного о себе",
]


# =========================================================
# DATABASE
# =========================================================

def db_connect():
    return sqlite3.connect(DB)


def init_db():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            registered_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            answers TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT
        )
    """)

    conn.commit()
    conn.close()

    # Главный админ всегда имеет доступ
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
        (ADMIN_ID, ADMIN_ID, datetime.now().isoformat())
    )

    conn.commit()
    conn.close()


def register_user(user):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO users
        (user_id, username, first_name, registered_at)
        VALUES (?, ?, ?, COALESCE(
            (SELECT registered_at FROM users WHERE user_id = ?),
            ?
        ))
    """, (
        user.id,
        user.username or "",
        user.first_name or "",
        user.id,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM admins WHERE user_id = ?",
        (user_id,)
    )

    result = cur.fetchone()

    conn.close()

    return result is not None


def add_admin(user_id, added_by):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
        (
            user_id,
            added_by,
            datetime.now().isoformat()
        )
    )

    changed = cur.rowcount > 0

    conn.commit()
    conn.close()

    return changed


def remove_admin(user_id):
    if user_id == ADMIN_ID:
        return False

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM admins WHERE user_id = ?",
        (user_id,)
    )

    changed = cur.rowcount > 0

    conn.commit()
    conn.close()

    return changed


def get_admins():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, added_by, added_at
        FROM admins
        ORDER BY added_at ASC
    """)

    admins = cur.fetchall()

    conn.close()

    return admins


def get_pending_application(user_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, username, answers, status, created_at
        FROM applications
        WHERE user_id = ? AND status = 'pending'
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))

    result = cur.fetchone()

    conn.close()

    return result


def get_application(app_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, user_id, username, answers, status, created_at
        FROM applications
        WHERE id = ?
    """, (app_id,))

    result = cur.fetchone()

    conn.close()

    return result


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Подать заявку", callback_data="apply")
        ],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="profile"),
            InlineKeyboardButton("📋 Моя заявка", callback_data="my_application")
        ],
        [
            InlineKeyboardButton("📢 О проекте", callback_data="about"),
            InlineKeyboardButton("💬 Поддержка", callback_data="support")
        ],
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Заявки", callback_data="admin_apps"),
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton("👮 Админы", callback_data="admin_admins")
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")
        ],
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    register_user(user)

    context.user_data.clear()

    text = (
        "🚀 <b>REWET HOST</b>\n\n"
        "Добро пожаловать!\n\n"
        "Здесь ты можешь узнать о проекте, "
        "получить помощь или подать заявку в команду."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🆘 <b>Помощь REWET HOST</b>\n\n"
        "/start — главное меню\n"
        "/help — помощь\n"
        "/commands — список команд\n"
        "/support — поддержка\n"
        "/errors — помощь с ошибками\n"
        "/chat — информация о чате\n"
    )

    if update.effective_user and is_admin(update.effective_user.id):
        text += (
            "\n👮 <b>Админ-команды:</b>\n"
            "/admin — админ-панель\n"
            "/setadmin ID — выдать админку\n"
            "/deladmin ID — снять админку\n"
            "/admins — список админов\n"
            "/stats — статистика\n"
            "/applications — заявки\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_command(update, context)


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💬 Поддержка REWET HOST:\n{SUPPORT_USERNAME}"
    )


async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛠️ <b>Помощь с ошибками</b>\n\n"
        "Отправь ошибку в чат и укажи:\n"
        "• текст ошибки;\n"
        "• что ты делал перед ошибкой;\n"
        "• версию сервера;\n"
        "• Pawn / плагины, если проблема с ними.\n\n"
        "Частые ошибки:\n"
        "🔴 error 017\n"
        "🔴 fatal error 100\n"
        "🔴 error 021\n"
        "🔴 error 025\n"
        "🔴 undefined symbol\n"
        "🔴 cannot read from file\n"
        "🔴 server.exe / crashdetect"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 <b>REWET HOST CHAT</b>\n\n"
        "В группе я могу помогать с ошибками и вопросами.\n\n"
        "Чтобы обратиться ко мне:\n"
        "• ответь на сообщение бота;\n"
        "• или напиши @имя_бота и вопрос.",
        parse_mode="HTML"
    )


# =========================================================
# ADMIN
# =========================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not is_admin(user.id):
        await update.message.reply_text("❌ У тебя нет доступа к админ-панели.")
        return

    await update.message.reply_text(
        "👮 <b>Админ-панель REWET HOST</b>",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )


# =========================================================
# ВЫДАЧА АДМИНКИ
# =========================================================

async def setadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Только главный админ
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Только главный администратор может выдавать админку."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❗ Использование:\n"
            "/setadmin ID\n\n"
            "Пример:\n"
            "/setadmin 123456789"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ ID должен состоять только из цифр."
        )
        return

    if target_id <= 0:
        await update.message.reply_text(
            "❌ Неверный Telegram ID."
        )
        return

    if target_id == ADMIN_ID:
        await update.message.reply_text(
            "ℹ️ Этот пользователь уже является главным администратором."
        )
        return

    added = add_admin(target_id, user.id)

    if not added:
        await update.message.reply_text(
            f"ℹ️ Пользователь <code>{target_id}</code> уже является администратором.",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"✅ Пользователь <code>{target_id}</code> получил админку.",
        parse_mode="HTML"
    )

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "👮 <b>Тебе выдали админку REWET HOST!</b>\n\n"
                "Теперь тебе доступны админские команды."
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass


# =========================================================
# СНЯТИЕ АДМИНКИ
# =========================================================

async def deladmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Только главный администратор может снимать админку."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❗ Использование:\n"
            "/deladmin ID\n\n"
            "Пример:\n"
            "/deladmin 123456789"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ ID должен состоять только из цифр."
        )
        return

    if target_id == ADMIN_ID:
        await update.message.reply_text(
            "❌ Нельзя снять админку с главного администратора."
        )
        return

    removed = remove_admin(target_id)

    if not removed:
        await update.message.reply_text(
            f"ℹ️ Пользователь <code>{target_id}</code> не найден среди админов.",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"✅ Админка пользователя <code>{target_id}</code> снята.",
        parse_mode="HTML"
    )

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="⚠️ Твоя админка REWET HOST была снята."
        )
    except Exception:
        pass


# =========================================================
# СПИСОК АДМИНОВ
# =========================================================

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not is_admin(user.id):
        await update.message.reply_text(
            "❌ У тебя нет доступа."
        )
        return

    admins = get_admins()

    if not admins:
        await update.message.reply_text(
            "👮 Администраторов пока нет."
        )
        return

    text = "👮 <b>Администраторы REWET HOST</b>\n\n"

    for index, (user_id, added_by, added_at) in enumerate(admins, 1):
        role = "👑 Главный админ" if user_id == ADMIN_ID else "🛡 Администратор"

        text += (
            f"{index}. {role}\n"
            f"ID: <code>{user_id}</code>\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# СТАТИСТИКА
# =========================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not is_admin(user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM applications")
    applications = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM applications WHERE status = 'pending'"
    )
    pending = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM applications WHERE status = 'accepted'"
    )
    accepted = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM applications WHERE status = 'rejected'"
    )
    rejected = cur.fetchone()[0]

    conn.close()

    await update.message.reply_text(
        "📊 <b>Статистика REWET HOST</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📋 Заявок: <b>{applications}</b>\n"
        f"🟡 Ожидают: <b>{pending}</b>\n"
        f"🟢 Принято: <b>{accepted}</b>\n"
        f"🔴 Отклонено: <b>{rejected}</b>",
        parse_mode="HTML"
    )


# =========================================================
# APPLICATION
# =========================================================

async def start_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    existing = get_pending_application(user.id)

    if existing:
        await update.effective_message.reply_text(
            "⏳ У тебя уже есть заявка, которая находится на рассмотрении."
        )
        return

    context.user_data["application_question"] = 0
    context.user_data["application_answers"] = []

    await update.effective_message.reply_text(
        f"📝 <b>Заявка в REWET HOST</b>\n\n"
        f"Вопрос 1 из {len(APPLICATION_QUESTIONS)}\n\n"
        f"<b>{APPLICATION_QUESTIONS[0]}</b>\n\n"
        "Напиши ответ сообщением.",
        parse_mode="HTML"
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("application_question", None)
    context.user_data.pop("application_answers", None)

    await update.message.reply_text(
        "❌ Заявка отменена."
    )


async def application_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not update.message:
        return

    if is_group(update):
        return

    if "application_question" not in context.user_data:
        return

    text = update.message.text.strip()

    if not text:
        return

    if len(text) > 1500:
        await update.message.reply_text(
            "❌ Ответ слишком длинный. Максимум 1500 символов."
        )
        return

    answers = context.user_data.get("application_answers", [])
    question_index = context.user_data["application_question"]

    answers.append(text)

    if question_index + 1 < len(APPLICATION_QUESTIONS):
        context.user_data["application_answers"] = answers
        context.user_data["application_question"] = question_index + 1

        next_question = APPLICATION_QUESTIONS[question_index + 1]

        await update.message.reply_text(
            f"📝 <b>Вопрос {question_index + 2} из {len(APPLICATION_QUESTIONS)}</b>\n\n"
            f"<b>{next_question}</b>",
            parse_mode="HTML"
        )

        return

    # Все ответы получены
    context.user_data["application_answers"] = answers

    result = "📋 <b>Проверь свою заявку:</b>\n\n"

    for i, answer in enumerate(answers):
        result += (
            f"<b>{i + 1}. {html.escape(APPLICATION_QUESTIONS[i])}</b>\n"
            f"{html.escape(answer)}\n\n"
        )

    result += "Отправить заявку?"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Отправить", callback_data="application_send"),
            InlineKeyboardButton("❌ Отменить", callback_data="application_cancel"),
        ]
    ])

    await update.message.reply_text(
        result,
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def send_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    answers = context.user_data.get("application_answers")

    if not answers:
        await query.edit_message_text(
            "❌ Данные заявки не найдены."
        )
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO applications
        (user_id, username, answers, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (
        user.id,
        user.username or "",
        repr(answers),
        datetime.now().isoformat()
    ))

    app_id = cur.lastrowid

    conn.commit()
    conn.close()

    context.user_data.pop("application_question", None)
    context.user_data.pop("application_answers", None)

    await query.edit_message_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Ожидай решения администрации REWET HOST.",
        parse_mode="HTML"
    )

    # Отправляем заявку главному админу
    application_text = (
        f"📋 <b>Новая заявка #{app_id}</b>\n\n"
        f"👤 Пользователь: "
        f"{html.escape(user.first_name or '')}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🔗 Username: @{html.escape(user.username or 'нет')}\n\n"
    )

    for i, answer in enumerate(answers):
        application_text += (
            f"<b>{i + 1}. {html.escape(APPLICATION_QUESTIONS[i])}</b>\n"
            f"{html.escape(answer)}\n\n"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Принять",
                callback_data=f"app_accept_{app_id}"
            ),
            InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"app_reject_{app_id}"
            )
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=application_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error("Не удалось отправить заявку админу: %s", e)


# =========================================================
# CALLBACKS
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if data == "apply":
        await start_application(update, context)
        return

    if data == "application_send":
        await send_application(update, context)
        return

    if data == "application_cancel":
        context.user_data.pop("application_question", None)
        context.user_data.pop("application_answers", None)

        await query.edit_message_text(
            "❌ Заявка отменена."
        )
        return

    if data == "profile":
        register_user(user)

        await query.edit_message_text(
            f"👤 <b>Твой профиль</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👤 Имя: {html.escape(user.first_name or '')}\n"
            f"🔗 Username: @{html.escape(user.username or 'нет')}\n\n"
            f"👮 Администратор: "
            f"{'Да' if is_admin(user.id) else 'Нет'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
            ])
        )
        return

    if data == "my_application":
        application = get_pending_application(user.id)

        if not application:
            await query.edit_message_text(
                "📋 У тебя нет заявки на рассмотрении.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
                ])
            )
            return

        await query.edit_message_text(
            f"📋 <b>Твоя заявка</b>\n\n"
            f"Номер: <code>#{application[0]}</code>\n"
            f"Статус: 🟡 На рассмотрении\n"
            f"Дата: {html.escape(application[4])}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
            ])
        )
        return

    if data == "about":
        await query.edit_message_text(
            "📢 <b>REWET HOST</b>\n\n"
            "Игровой хостинг и проект для игроков и разработчиков.\n\n"
            "🚀 Развитие\n"
            "🛠️ Поддержка\n"
            "🎮 Игровые серверы\n"
            "👥 Команда проекта",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
            ])
        )
        return

    if data == "support":
        await query.edit_message_text(
            f"💬 <b>Поддержка</b>\n\n"
            f"{SUPPORT_USERNAME}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
            ])
        )
        return

    # -----------------------------------------------------
    # ADMIN CALLBACKS
    # -----------------------------------------------------

    if data.startswith("admin_") and not is_admin(user.id):
        await query.edit_message_text(
            "❌ У тебя нет доступа к админ-панели."
        )
        return

    if data == "admin_apps":
        conn = db_connect()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, user_id, username, status, created_at
            FROM applications
            ORDER BY id DESC
            LIMIT 20
        """)

        apps = cur.fetchall()

        conn.close()

        if not apps:
            text = "📋 Заявок пока нет."
        else:
            text = "📋 <b>Последние заявки:</b>\n\n"

            for app in apps:
                status = {
                    "pending": "🟡",
                    "accepted": "🟢",
                    "rejected": "🔴"
                }.get(app[3], "⚪")

                text += (
                    f"{status} #{app[0]} — "
                    f"<code>{app[1]}</code>\n"
                )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_back")]
            ])
        )
        return

    if data == "admin_stats":
        conn = db_connect()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM applications")
        applications = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM applications WHERE status='pending'"
        )
        pending = cur.fetchone()[0]

        conn.close()

        await query.edit_message_text(
            "📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: <b>{users}</b>\n"
            f"📋 Заявок: <b>{applications}</b>\n"
            f"🟡 На рассмотрении: <b>{pending}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_back")]
            ])
        )
        return

    if data == "admin_users":
        conn = db_connect()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]

        conn.close()

        await query.edit_message_text(
            f"👥 <b>Пользователи</b>\n\n"
            f"Всего зарегистрировано: <b>{users}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_back")]
            ])
        )
        return

    if data == "admin_admins":
        admins = get_admins()

        text = "👮 <b>Администраторы</b>\n\n"

        for admin in admins:
            role = "👑 Главный" if admin[0] == ADMIN_ID else "🛡 Админ"
            text += f"{role}: <code>{admin[0]}</code>\n"

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_back")]
            ])
        )
        return

    if data == "admin_back":
        await query.edit_message_text(
            "👮 <b>Админ-панель REWET HOST</b>",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )
        return

    if data == "back_main":
        await query.edit_message_text(
            "🚀 <b>REWET HOST</b>\n\n"
            "Главное меню:",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        return

    # -----------------------------------------------------
    # ACCEPT / REJECT APPLICATION
    # -----------------------------------------------------

    if data.startswith("app_accept_") or data.startswith("app_reject_"):
        if not is_admin(user.id):
            await query.edit_message_text(
                "❌ Нет доступа."
            )
            return

        try:
            app_id = int(data.split("_")[-1])
        except ValueError:
            return

        application = get_application(app_id)

        if not application:
            await query.edit_message_text(
                "❌ Заявка не найдена."
            )
            return

        if application[4] != "pending":
            await query.edit_message_text(
                "ℹ️ Эта заявка уже обработана."
            )
            return

        accepted = data.startswith("app_accept_")
        new_status = "accepted" if accepted else "rejected"

        conn = db_connect()
        cur = conn.cursor()

        cur.execute(
            "UPDATE applications SET status = ? WHERE id = ?",
            (new_status, app_id)
        )

        conn.commit()
        conn.close()

        if accepted:
            status_text = "🟢 Заявка принята!"
            user_text = (
                "🎉 <b>Поздравляем!</b>\n\n"
                "Твоя заявка в команду REWET HOST была <b>принята</b>."
            )
        else:
            status_text = "🔴 Заявка отклонена."
            user_text = (
                "❌ <b>Заявка отклонена.</b>\n\n"
                "К сожалению, твоя заявка в REWET HOST "
                "не была принята."
            )

        await query.edit_message_text(
            f"{status_text}\n\n"
            f"Заявка #{app_id}\n"
            f"Пользователь: <code>{application[1]}</code>",
            parse_mode="HTML"
        )

        try:
            await context.bot.send_message(
                chat_id=application[1],
                text=user_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error("Не удалось уведомить пользователя: %s", e)

        return


# =========================================================
# GROUP CHAT
# =========================================================

def is_group(update: Update):
    chat = update.effective_chat

    if not chat:
        return False

    return chat.type in ("group", "supergroup")


def is_bot_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message or not message.text:
        return False

    if not BOT_USERNAME:
        return False

    pattern = rf"@{re.escape(BOT_USERNAME)}\b"

    return re.search(
        pattern,
        message.text,
        flags=re.IGNORECASE
    ) is not None


def is_reply_to_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message or not message.reply_to_message:
        return False

    replied = message.reply_to_message

    if not replied.from_user:
        return False

    return replied.from_user.id == context.bot.id


def check_group_cooldown(user_id):
    now = datetime.now().timestamp()

    last_time = group_cooldowns.get(user_id, 0)

    if now - last_time < GROUP_COOLDOWN:
        return False

    group_cooldowns[user_id] = now

    return True


def detect_error(text):
    lowered = text.lower()

    errors = [
        "error 017",
        "error 021",
        "error 025",
        "fatal error 100",
        "undefined symbol",
        "cannot read from file",
        "server.exe",
        "crashdetect",
        "warning 217",
    ]

    for error in errors:
        if error in lowered:
            return error

    return None


async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return

    message = update.message

    if not message or not message.text:
        return

    mentioned = is_bot_mentioned(update, context)
    replied = is_reply_to_bot(update, context)

    if not mentioned and not replied:
        return

    user = update.effective_user

    if not user:
        return

    if not check_group_cooldown(user.id):
        return

    text = message.text.strip()

    if BOT_USERNAME:
        text = re.sub(
            rf"@{re.escape(BOT_USERNAME)}\b",
            "",
            text,
            flags=re.IGNORECASE
        ).strip()

    if not text:
        await message.reply_text(
            "👋 Да, я здесь. Напиши свой вопрос."
        )
        return

    error = detect_error(text)

    if error:
        await message.reply_text(
            f"🛠️ Похоже, у тебя ошибка <b>{html.escape(error)}</b>.\n\n"
            "Пришли полный текст ошибки или скриншот, "
            "и я помогу разобраться.",
            parse_mode="HTML"
        )
        return

    await message.reply_text(
        "💬 Получил сообщение.\n\n"
        "Сейчас я работаю без ИИ, поэтому могу помочь "
        "с командами бота и распространёнными ошибками "
        "Pawn/SA-MP."
    )


# =========================================================
# POST INIT
# =========================================================

async def post_init(application: Application):
    global BOT_USERNAME

    me = await application.bot.get_me()

    BOT_USERNAME = me.username or ""

    logger.info(
        "Бот запущен: @%s",
        BOT_USERNAME
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(
        "Ошибка при обработке update:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не найден в переменных окружения."
        )

    init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("errors", errors_command))
    app.add_handler(CommandHandler("chat", chat_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Админ-команды
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("applications", stats_command))

    # Управление админами
    app.add_handler(CommandHandler("setadmin", setadmin_command))
    app.add_handler(CommandHandler("deladmin", deladmin_command))
    app.add_handler(CommandHandler("admins", admins_command))

    # Callback-кнопки
    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    # Текст заявок
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            application_text_handler
        )
    )

    # Группа
    # Ловим обычный текст, а внутри проверяем:
    # упоминание бота или ответ на сообщение бота.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            group_message_handler
        )
    )

    app.add_error_handler(error_handler)

    logger.info("REWET HOST BOT запускается...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
