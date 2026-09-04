import os
import re
import sqlite3
import logging
import html
import random
import asyncio
from datetime import datetime, timedelta

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
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

CHANNEL_USERNAME = "@rewethost"
CHANNEL_URL = "https://t.me/rewethost"

GROUP_COOLDOWN = 5

BOT_USERNAME = ""

group_cooldowns = {}
spam_data = {}
giveaways = {}

MAX_WARNINGS = 3

# Запрещённые слова
BAD_WORDS = {
    "хуй",
    "хуйн",
    "пизд",
    "ебл",
    "ебан",
    "бляд",
    "бля",
    "сука",
    "шлюха",
    "мразь",
}

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            chat_id INTEGER,
            user_id INTEGER,
            count INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            chat_id INTEGER,
            user_id INTEGER,
            messages INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    conn.commit()

    cur.execute(
        """
        INSERT OR IGNORE INTO admins
        (user_id, added_by, added_at)
        VALUES (?, ?, ?)
        """,
        (
            ADMIN_ID,
            ADMIN_ID,
            datetime.now().isoformat()
        )
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
        """
        INSERT OR IGNORE INTO admins
        (user_id, added_by, added_at)
        VALUES (?, ?, ?)
        """,
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


# =========================================================
# WARNINGS
# =========================================================

def get_warns(chat_id, user_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT count
        FROM warnings
        WHERE chat_id = ? AND user_id = ?
        """,
        (chat_id, user_id)
    )

    result = cur.fetchone()

    conn.close()

    return result[0] if result else 0


def add_warn(chat_id, user_id):
    current = get_warns(chat_id, user_id)
    new_count = current + 1

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR REPLACE INTO warnings
        (chat_id, user_id, count)
        VALUES (?, ?, ?)
        """,
        (chat_id, user_id, new_count)
    )

    conn.commit()
    conn.close()

    return new_count


def remove_warn(chat_id, user_id):
    current = get_warns(chat_id, user_id)

    if current <= 0:
        return 0

    new_count = current - 1

    conn = db_connect()
    cur = conn.cursor()

    if new_count <= 0:
        cur.execute(
            """
            DELETE FROM warnings
            WHERE chat_id = ? AND user_id = ?
            """,
            (chat_id, user_id)
        )
    else:
        cur.execute(
            """
            UPDATE warnings
            SET count = ?
            WHERE chat_id = ? AND user_id = ?
            """,
            (new_count, chat_id, user_id)
        )

    conn.commit()
    conn.close()

    return new_count


# =========================================================
# ACTIVITY / RATING
# =========================================================

def add_activity(chat_id, user_id, points=1):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO activity
        (chat_id, user_id, messages, points)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET
            messages = messages + 1,
            points = points + ?
        """,
        (
            chat_id,
            user_id,
            points,
            points
        )
    )

    conn.commit()
    conn.close()


def get_top_users(chat_id, limit=10):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, messages, points
        FROM activity
        WHERE chat_id = ?
        ORDER BY points DESC
        LIMIT ?
        """,
        (chat_id, limit)
    )

    result = cur.fetchall()
    conn.close()

    return result


# =========================================================
# APPLICATION
# =========================================================

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
# МЕНЮ
# =========================================================

def main_menu():
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
                callback_data="my_application"
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


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📋 Заявки",
                callback_data="admin_apps"
            ),
            InlineKeyboardButton(
                "📊 Статистика",
                callback_data="admin_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Пользователи",
                callback_data="admin_users"
            ),
            InlineKeyboardButton(
                "👮 Админы",
                callback_data="admin_admins"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Главное меню",
                callback_data="back_main"
            )
        ],
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not update.message:
        return

    register_user(user)

    context.user_data.clear()

    await update.message.reply_text(
        "🚀 <b>REWET HOST</b>\n\n"
        "Добро пожаловать!\n\n"
        "Здесь ты можешь узнать о проекте, "
        "получить помощь или подать заявку в команду.",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = (
        "🆘 <b>REWET HOST</b>\n\n"
        "/start — главное меню\n"
        "/help — помощь\n"
        "/commands — команды\n"
        "/support — поддержка\n"
        "/errors — ошибки\n"
        "/chat — информация о чате\n"
        "/top — рейтинг участников\n"
        "/warns — предупреждения\n"
    )

    if update.effective_user and is_admin(update.effective_user.id):
        text += (
            "\n👑 <b>АДМИН-КОМАНДЫ</b>\n\n"
            "/admin\n"
            "/stats\n"
            "/setadmin ID\n"
            "/deladmin ID\n"
            "/admins\n"
            "/broadcast текст\n\n"
            "🛡 <b>МОДЕРАЦИЯ</b>\n"
            "/promote ID\n"
            "/demote ID\n"
            "/ban ID\n"
            "/unban ID\n"
            "/kick ID\n"
            "/mute ID 10m\n"
            "/unmute ID\n"
            "/warn ID\n"
            "/unwarn ID\n"
            "/clear 20\n"
            "/userinfo ID\n\n"
            "🎁 <b>РОЗЫГРЫШ</b>\n"
            "/giveaway секунды приз\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


async def commands_command(update, context):
    await help_command(update, context)


async def support_command(update, context):
    if update.message:
        await update.message.reply_text(
            f"💬 Поддержка REWET HOST:\n{SUPPORT_USERNAME}"
        )


async def errors_command(update, context):
    if update.message:
        await update.message.reply_text(
            "🛠️ <b>Помощь с ошибками</b>\n\n"
            "Отправь мне или в чат полный текст ошибки.\n\n"
            "Я распознаю:\n"
            "🔴 error 017\n"
            "🔴 error 021\n"
            "🔴 error 025\n"
            "🔴 fatal error 100\n"
            "🔴 undefined symbol\n"
            "🔴 cannot read from file\n"
            "🔴 crashdetect\n"
            "🔴 warning 217",
            parse_mode="HTML"
        )


async def chat_command(update, context):
    if update.message:
        await update.message.reply_text(
            "💬 <b>REWET HOST CHAT</b>\n\n"
            "Напиши:\n"
            "REWET привет\n"
            "REWET как дела?\n"
            "REWET помоги\n"
            "REWET кто лох?\n\n"
            "🔗 Ссылки автоматически удаляются.",
            parse_mode="HTML"
        )


# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_command(update, context):
    user = update.effective_user

    if not update.message:
        return

    if not user or not is_admin(user.id):
        await update.message.reply_text(
            "❌ Нет доступа."
        )
        return

    await update.message.reply_text(
        "👮 <b>Админ-панель REWET HOST</b>",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )


# =========================================================
# SETADMIN / DELADMIN
# =========================================================

async def setadmin_command(update, context):
    user = update.effective_user

    if not update.message:
        return

    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Только главный администратор."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /setadmin ID"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ ID должен быть числом."
        )
        return

    if target_id == ADMIN_ID:
        await update.message.reply_text(
            "ℹ️ Это главный администратор."
        )
        return

    if add_admin(target_id, user.id):
        await update.message.reply_text(
            f"✅ <code>{target_id}</code> получил админку бота.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "ℹ️ Этот пользователь уже админ."
        )


async def deladmin_command(update, context):
    user = update.effective_user

    if not update.message:
        return

    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Только главный администратор."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /deladmin ID"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ ID должен быть числом."
        )
        return

    if remove_admin(target_id):
        await update.message.reply_text(
            f"✅ Админка <code>{target_id}</code> снята.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "❌ Админ не найден."
        )


async def admins_command(update, context):
    if not update.message:
        return

    user = update.effective_user

    if not user or not is_admin(user.id):
        await update.message.reply_text(
            "❌ Нет доступа."
        )
        return

    admins = get_admins()

    text = "👮 <b>Администраторы бота</b>\n\n"

    for admin in admins:
        role = (
            "👑 Главный"
            if admin[0] == ADMIN_ID
            else "🛡 Админ"
        )

        text += f"{role}: <code>{admin[0]}</code>\n"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# PROMOTE / DEMOTE
# =========================================================

def get_target_user_id(update, context):
    message = update.effective_message

    if not message:
        return None

    if message.reply_to_message:
        if message.reply_to_message.from_user:
            return message.reply_to_message.from_user.id

    if context.args:
        try:
            target_id = int(context.args[0])
            if target_id > 0:
                return target_id
        except ValueError:
            pass

    return None


async def promote_user(chat_id, target_id, bot):
    await bot.promote_chat_member(
        chat_id=chat_id,
        user_id=target_id,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=True,
        can_restrict_members=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_change_info=False,
        can_promote_members=False,
        can_manage_topics=True,
    )


async def promote_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if user.id != ADMIN_ID:
        await message.reply_text(
            "❌ Только главный администратор может повышать пользователей."
        )
        return

    if chat.type not in ("group", "supergroup"):
        await message.reply_text(
            "❌ Команда работает только в чате."
        )
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "❗ Ответь /promote на сообщение пользователя "
            "или используй /promote ID."
        )
        return

    try:
        await promote_user(
            chat.id,
            target_id,
            context.bot
        )

        await message.reply_text(
            f"👑 <code>{target_id}</code> теперь администратор чата.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Promote error")

        await message.reply_text(
            "❌ Не получилось повысить.\n\n"
            "Проверь, что бот сам администратор и имеет "
            "право добавлять новых администраторов."
        )


async def demote_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if user.id != ADMIN_ID:
        await message.reply_text(
            "❌ Только главный администратор."
        )
        return

    if chat.type not in ("group", "supergroup"):
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "❗ Ответь /demote на сообщение или укажи ID."
        )
        return

    try:
        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=target_id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_change_info=False,
            can_promote_members=False,
            can_manage_topics=False,
        )

        await message.reply_text(
            f"✅ Админка <code>{target_id}</code> снята.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Demote error")

        await message.reply_text(
            "❌ Не удалось снять админку."
        )


# =========================================================
# BAN / UNBAN / KICK
# =========================================================

async def ban_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование: /ban ID\n"
            "Или ответь /ban на сообщение."
        )
        return

    try:
        await context.bot.ban_chat_member(
            chat.id,
            target_id
        )

        await message.reply_text(
            f"🔨 Пользователь <code>{target_id}</code> заблокирован.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Ban error")
        await message.reply_text(
            "❌ Не удалось заблокировать пользователя."
        )


async def unban_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование: /unban ID"
        )
        return

    try:
        await context.bot.unban_chat_member(
            chat.id,
            target_id,
            only_if_banned=True
        )

        await message.reply_text(
            f"✅ Пользователь <code>{target_id}</code> разблокирован.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Unban error")
        await message.reply_text(
            "❌ Не удалось разблокировать."
        )


async def kick_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование: /kick ID\n"
            "Или ответь /kick на сообщение."
        )
        return

    try:
        await context.bot.ban_chat_member(
            chat.id,
            target_id
        )

        await context.bot.unban_chat_member(
            chat.id,
            target_id
        )

        await message.reply_text(
            f"👢 Пользователь <code>{target_id}</code> исключён.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Kick error")
        await message.reply_text(
            "❌ Не удалось исключить."
        )


# =========================================================
# MUTE / UNMUTE
# =========================================================

def parse_duration(value):
    match = re.match(
        r"^(\d+)(s|m|h|d)$",
        value.lower()
    )

    if not match:
        return None

    number = int(match.group(1))
    unit = match.group(2)

    if unit == "s":
        return timedelta(seconds=number)

    if unit == "m":
        return timedelta(minutes=number)

    if unit == "h":
        return timedelta(hours=number)

    if unit == "d":
        return timedelta(days=number)

    return None


async def mute_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование:\n"
            "/mute ID 10m\n\n"
            "Или ответь /mute 10m на сообщение."
        )
        return

    duration = None

    if context.args:
        if message.reply_to_message:
            if len(context.args) >= 1:
                duration = parse_duration(
                    context.args[0]
                )
        elif len(context.args) >= 2:
            duration = parse_duration(
                context.args[1]
            )

    if not duration:
        await message.reply_text(
            "❌ Укажи время.\n"
            "Пример: /mute ID 10m\n"
            "Или ответь /mute 10m."
        )
        return

    until = datetime.now() + duration

    try:
        await context.bot.restrict_chat_member(
            chat.id,
            target_id,
            permissions=ChatPermissions(
                can_send_messages=False
            ),
            until_date=until
        )

        await message.reply_text(
            f"🔇 <code>{target_id}</code> получил мут на "
            f"<b>{duration}</b>.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Mute error")
        await message.reply_text(
            "❌ Не удалось выдать мут."
        )


async def unmute_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование: /unmute ID"
        )
        return

    try:
        await context.bot.restrict_chat_member(
            chat.id,
            target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )

        await message.reply_text(
            f"🔊 Мут с <code>{target_id}</code> снят.",
            parse_mode="HTML"
        )

    except Exception:
        logger.exception("Unmute error")
        await message.reply_text(
            "❌ Не удалось снять мут."
        )


# =========================================================
# WARN
# =========================================================

async def warn_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование: /warn ID\n"
            "Или ответь /warn."
        )
        return

    if target_id == ADMIN_ID:
        await message.reply_text(
            "❌ Нельзя выдать предупреждение главному админу."
        )
        return

    count = add_warn(chat.id, target_id)

    if count >= MAX_WARNINGS:

        try:
            await context.bot.restrict_chat_member(
                chat.id,
                target_id,
                permissions=ChatPermissions(
                    can_send_messages=False
                ),
                until_date=datetime.now() + timedelta(hours=1)
            )

            await message.reply_text(
                f"🔇 Пользователь <code>{target_id}</code> "
                f"получил {count} предупреждения.\n\n"
                "Автоматический мут на 1 час.",
                parse_mode="HTML"
            )

        except Exception:
            await message.reply_text(
                f"⚠️ Предупреждений: {count}/3"
            )

    else:
        await message.reply_text(
            f"⚠️ Пользователь <code>{target_id}</code> "
            f"получил предупреждение.\n\n"
            f"Предупреждений: <b>{count}/{MAX_WARNINGS}</b>",
            parse_mode="HTML"
        )


async def unwarn_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "Использование: /unwarn ID"
        )
        return

    count = remove_warn(
        chat.id,
        target_id
    )

    await message.reply_text(
        f"✅ Предупреждение снято.\n"
        f"Теперь: <b>{count}/{MAX_WARNINGS}</b>",
        parse_mode="HTML"
    )


async def warns_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    target_id = get_target_user_id(
        update,
        context
    )

    if not target_id:
        target_id = user.id

    count = get_warns(
        chat.id,
        target_id
    )

    await message.reply_text(
        f"⚠️ Предупреждений: <b>{count}/{MAX_WARNINGS}</b>",
        parse_mode="HTML"
    )


# =========================================================
# CLEAR
# =========================================================

async def clear_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    if not context.args:
        await message.reply_text(
            "Использование: /clear 20"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await message.reply_text(
            "❌ Количество должно быть числом."
        )
        return

    if amount < 1:
        return

    if amount > 100:
        amount = 100

    deleted = 0

    try:
        current_id = message.message_id

        for i in range(amount):
            msg_id = current_id - i

            try:
                await context.bot.delete_message(
                    chat.id,
                    msg_id
                )

                deleted += 1

            except Exception:
                pass

        info = await context.bot.send_message(
            chat.id,
            f"🧹 Удалено сообщений: {deleted}"
        )

        await asyncio.sleep(3)

        try:
            await info.delete()
        except Exception:
            pass

    except Exception:
        logger.exception("Clear error")


# =========================================================
# USERINFO
# =========================================================

async def userinfo_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

    target_id = get_target_user_id(
        update,
        context
    )

    if not target_id:
        target_id = user.id

    try:
        member = await context.bot.get_chat_member(
            chat.id,
            target_id
        )

        status = member.status

        warns = get_warns(
            chat.id,
            target_id
        )

        await message.reply_text(
            "👤 <b>Информация</b>\n\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"👮 Статус: <b>{status}</b>\n"
            f"⚠️ Варны: <b>{warns}/{MAX_WARNINGS}</b>",
            parse_mode="HTML"
        )

    except Exception:
        await message.reply_text(
            "❌ Пользователь не найден."
        )


# =========================================================
# TOP
# =========================================================

async def top_command(update, context):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in ("group", "supergroup"):
        await message.reply_text(
            "🏆 Рейтинг доступен в чате."
        )
        return

    top = get_top_users(chat.id)

    if not top:
        await message.reply_text(
            "🏆 Пока рейтинг пуст."
        )
        return

    text = "🏆 <b>ТОП REWET HOST</b>\n\n"

    for index, row in enumerate(top, 1):

        user_id = row[0]

        try:
            member = await context.bot.get_chat_member(
                chat.id,
                user_id
            )

            name = html.escape(
                member.user.first_name or "Пользователь"
            )

        except Exception:
            name = f"ID {user_id}"

        text += (
            f"{index}. <b>{name}</b>\n"
            f"   ⭐ {row[2]} очков | 💬 {row[1]} сообщений\n\n"
        )

    await message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# BROADCAST
# =========================================================

async def broadcast_command(update, context):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if user.id != ADMIN_ID:
        await message.reply_text(
            "❌ Только главный администратор."
        )
        return

    if not context.args:
        await message.reply_text(
            "Использование:\n"
            "/broadcast текст"
        )
        return

    text = " ".join(context.args)

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM users"
    )

    users = cur.fetchall()

    conn.close()

    sent = 0
    failed = 0

    await message.reply_text(
        f"📢 Начинаю рассылку.\n"
        f"Получателей: {len(users)}"
    )

    for row in users:
        target_id = row[0]

        try:
            await context.bot.send_message(
                target_id,
                f"📢 <b>REWET HOST</b>\n\n{text}",
                parse_mode="HTML"
            )

            sent += 1

            await asyncio.sleep(0.05)

        except Exception:
            failed += 1

    await message.reply_text(
        "✅ <b>Рассылка завершена</b>\n\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML"
    )


# =========================================================
# STATS
# =========================================================

async def stats_command(update, context):
    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    if not is_admin(user.id):
        await message.reply_text("❌ Нет доступа.")
        return

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

    cur.execute(
        "SELECT COUNT(*) FROM applications WHERE status='accepted'"
    )
    accepted = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM applications WHERE status='rejected'"
    )
    rejected = cur.fetchone()[0]

    cur.execute(
        "SELECT SUM(messages) FROM activity"
    )
    messages = cur.fetchone()[0] or 0

    conn.close()

    await message.reply_text(
        "📊 <b>REWET HOST</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"💬 Сообщений: <b>{messages}</b>\n"
        f"📋 Заявок: <b>{applications}</b>\n"
        f"🟡 Ожидают: <b>{pending}</b>\n"
        f"🟢 Принято: <b>{accepted}</b>\n"
        f"🔴 Отклонено: <b>{rejected}</b>",
        parse_mode="HTML"
    )


# =========================================================
# GIVEAWAY
# =========================================================

async def giveaway_command(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if not is_admin(user.id):
        await message.reply_text(
            "❌ Только администратор."
        )
        return

    if chat.type not in ("group", "supergroup"):
        await message.reply_text(
            "❌ Розыгрыш запускается в группе."
        )
        return

    if len(context.args) < 2:
        await message.reply_text(
            "Использование:\n"
            "/giveaway 60 1000 рублей\n\n"
            "Первое число — секунды.\n"
            "Остальное — приз."
        )
        return

    try:
        seconds = int(context.args[0])
    except ValueError:
        await message.reply_text(
            "❌ Время должно быть числом."
        )
        return

    if seconds < 10:
        await message.reply_text(
            "❌ Минимум 10 секунд."
        )
        return

    prize = " ".join(context.args[1:])

    giveaway_id = f"{chat.id}_{message.message_id}"

    giveaways[giveaway_id] = {
        "chat_id": chat.id,
        "participants": set(),
        "prize": prize,
        "message_id": None,
        "active": True,
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎉 Участвовать",
                callback_data=f"giveaway_{giveaway_id}"
            )
        ]
    ])

    giveaway_message = await message.reply_text(
        f"🎁 <b>РОЗЫГРЫШ REWET HOST</b>\n\n"
        f"🏆 Приз: <b>{html.escape(prize)}</b>\n"
        f"⏳ Время: <b>{seconds} сек.</b>\n\n"
        "Нажми кнопку ниже, чтобы участвовать!",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    giveaways[giveaway_id]["message_id"] = giveaway_message.message_id

    await asyncio.sleep(seconds)

    data = giveaways.get(giveaway_id)

    if not data or not data["active"]:
        return

    data["active"] = False

    participants = list(data["participants"])

    if not participants:
        await context.bot.send_message(
            chat.id,
            "🎁 Розыгрыш завершён.\n\n"
            "❌ Участников не было."
        )
        return

    winner_id = random.choice(participants)

    try:
        winner = await context.bot.get_chat_member(
            chat.id,
            winner_id
        )

        winner_name = html.escape(
            winner.user.first_name or "Победитель"
        )

    except Exception:
        winner_name = f"ID {winner_id}"

    await context.bot.send_message(
        chat.id,
        "🎉 <b>РОЗЫГРЫШ ЗАВЕРШЁН!</b>\n\n"
        f"🏆 Приз: <b>{html.escape(prize)}</b>\n"
        f"👑 Победитель: <b>{winner_name}</b>\n\n"
        "Поздравляем! 🎊",
        parse_mode="HTML"
    )


# =========================================================
# SUBSCRIPTION
# =========================================================

async def check_subscription(user_id, bot):
    try:
        member = await bot.get_chat_member(
            CHANNEL_USERNAME,
            user_id
        )

        return (
            member.status in (
                "member",
                "administrator",
                "creator"
            )
            or getattr(member, "is_member", False)
        )

    except Exception as e:
        logger.error(
            "Subscription error: %s",
            e
        )

        return False


def subscription_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Подписаться на канал",
                url=CHANNEL_URL
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Я подписался",
                callback_data="check_subscription"
            )
        ]
    ])


async def restrict_user_in_chat(chat_id, user_id, bot):
    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
        )
    )


async def unrestrict_user_in_chat(chat_id, user_id, bot):
    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        )
    )


# =========================================================
# НОВЫЙ УЧАСТНИК
# =========================================================

async def new_member_handler(update, context):
    message = update.message

    if not message:
        return

    chat = update.effective_chat

    if not chat:
        return

    for new_user in message.new_chat_members:

        if new_user.is_bot:
            continue

        register_user(new_user)

        try:
            await restrict_user_in_chat(
                chat.id,
                new_user.id,
                context.bot
            )
        except Exception:
            logger.exception(
                "Не удалось ограничить нового пользователя"
            )

        name = html.escape(
            new_user.first_name or "друг"
        )

        await message.reply_text(
            f"👋 <b>Привет, {name}!</b>\n\n"
            "Добро пожаловать в <b>REWET HOST</b>! 🚀\n\n"
            "🔒 Чтобы писать в чат, сначала "
            "подпишись на наш канал:\n"
            f"📢 <b>{CHANNEL_USERNAME}</b>\n\n"
            "После подписки нажми кнопку "
            "«✅ Я подписался».",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )


# =========================================================
# CALLBACKS
# =========================================================

async def callbacks(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    # -----------------------------------------------------
    # ПОДПИСКА
    # -----------------------------------------------------

    if data == "check_subscription":

        chat = update.effective_chat

        if not chat:
            return

        subscribed = await check_subscription(
            user.id,
            context.bot
        )

        if not subscribed:
            await query.answer(
                "❌ Я не вижу подписку.",
                show_alert=True
            )
            return

        try:
            await unrestrict_user_in_chat(
                chat.id,
                user.id,
                context.bot
            )

            await query.edit_message_text(
                f"🎉 <b>{html.escape(user.first_name or 'Друг')}</b>, "
                "подписка подтверждена!\n\n"
                "🔓 Теперь ты можешь писать в чат.\n"
                "Добро пожаловать в REWET HOST! 🚀",
                parse_mode="HTML"
            )

        except Exception:
            logger.exception("Unrestrict error")

            await query.answer(
                "❌ Бот не может открыть доступ. "
                "Проверь права бота.",
                show_alert=True
            )

        return

    # -----------------------------------------------------
    # GIVEAWAY
    # -----------------------------------------------------

    if data.startswith("giveaway_"):

        giveaway_id = data[len("giveaway_"):]

        giveaway = giveaways.get(giveaway_id)

        if not giveaway:
            await query.answer(
                "❌ Розыгрыш не найден.",
                show_alert=True
            )
            return

        if not giveaway["active"]:
            await query.answer(
                "❌ Розыгрыш уже завершён.",
                show_alert=True
            )
            return

        giveaway["participants"].add(
            user.id
        )

        await query.answer(
            "🎉 Ты участвуешь!",
            show_alert=True
        )

        return

    # -----------------------------------------------------
    # APPLICATION
    # -----------------------------------------------------

    if data == "apply":

        context.user_data["application_question"] = 0
        context.user_data["application_answers"] = []

        await query.edit_message_text(
            f"📝 <b>Заявка в REWET HOST</b>\n\n"
            f"Вопрос 1 из {len(APPLICATION_QUESTIONS)}\n\n"
            f"<b>{APPLICATION_QUESTIONS[0]}</b>",
            parse_mode="HTML"
        )
        return

    if data == "application_send":

        answers = context.user_data.get(
            "application_answers"
        )

        if not answers:
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

        context.user_data.clear()

        await query.edit_message_text(
            "✅ <b>Заявка отправлена!</b>\n\n"
            "Ожидай решения администрации.",
            parse_mode="HTML"
        )

        application_text = (
            f"📋 <b>Новая заявка #{app_id}</b>\n\n"
            f"👤 {html.escape(user.first_name or '')}\n"
            f"🆔 <code>{user.id}</code>\n\n"
        )

        for i, answer in enumerate(answers):
            application_text += (
                f"<b>{i + 1}. "
                f"{html.escape(APPLICATION_QUESTIONS[i])}</b>\n"
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
                ADMIN_ID,
                application_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            logger.exception(
                "Application send error"
            )

        return

    if data == "application_cancel":

        context.user_data.clear()

        await query.edit_message_text(
            "❌ Заявка отменена."
        )
        return

    # -----------------------------------------------------
    # PROFILE
    # -----------------------------------------------------

    if data == "profile":

        register_user(user)

        await query.edit_message_text(
            f"👤 <b>Профиль</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👤 Имя: {html.escape(user.first_name or '')}\n"
            f"🔗 @{html.escape(user.username or 'нет')}\n"
            f"👮 Админ: {'Да' if is_admin(user.id) else 'Нет'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="back_main"
                    )
                ]
            ])
        )
        return

    # -----------------------------------------------------
    # MY APPLICATION
    # -----------------------------------------------------

    if data == "my_application":

        application = get_pending_application(
            user.id
        )

        if not application:
            await query.edit_message_text(
                "📋 Заявок на рассмотрении нет.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 Назад",
                            callback_data="back_main"
                        )
                    ]
                ])
            )
            return

        await query.edit_message_text(
            f"📋 <b>Твоя заявка</b>\n\n"
            f"Номер: #{application[0]}\n"
            f"Статус: 🟡 На рассмотрении",
            parse_mode="HTML"
        )
        return

    # -----------------------------------------------------
    # ABOUT
    # -----------------------------------------------------

    if data == "about":

        await query.edit_message_text(
            "📢 <b>REWET HOST</b>\n\n"
            "🚀 Игровой хостинг\n"
            "🎮 Игровые серверы\n"
            "🛠️ Поддержка\n"
            "👥 Команда проекта",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="back_main"
                    )
                ]
            ])
        )
        return

    # -----------------------------------------------------
    # SUPPORT
    # -----------------------------------------------------

    if data == "support":

        await query.edit_message_text(
            f"💬 <b>Поддержка</b>\n\n{SUPPORT_USERNAME}",
            parse_mode="HTML"
        )
        return

    # -----------------------------------------------------
    # ADMIN
    # -----------------------------------------------------

    if data.startswith("admin_"):

        if not is_admin(user.id):
            await query.edit_message_text(
                "❌ Нет доступа."
            )
            return

    if data == "admin_apps":

        conn = db_connect()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, user_id, status
            FROM applications
            ORDER BY id DESC
            LIMIT 20
        """)

        apps = cur.fetchall()

        conn.close()

        text = "📋 <b>Заявки</b>\n\n"

        if not apps:
            text += "Заявок нет."

        for app in apps:

            status = {
                "pending": "🟡",
                "accepted": "🟢",
                "rejected": "🔴"
            }.get(app[2], "⚪")

            text += (
                f"{status} #{app[0]} — "
                f"<code>{app[1]}</code>\n"
            )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Админ-панель",
                        callback_data="admin_back"
                    )
                ]
            ])
        )
        return

    if data == "admin_stats":

        await query.message.reply_text(
            "Используй /stats для полной статистики."
        )
        return

    if data == "admin_users":

        conn = db_connect()
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*) FROM users"
        )

        users = cur.fetchone()[0]

        conn.close()

        await query.edit_message_text(
            f"👥 Пользователей: <b>{users}</b>",
            parse_mode="HTML"
        )
        return

    if data == "admin_admins":

        admins = get_admins()

        text = "👮 <b>Админы</b>\n\n"

        for admin in admins:
            text += f"<code>{admin[0]}</code>\n"

        await query.edit_message_text(
            text,
            parse_mode="HTML"
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
    # APPLICATION ACCEPT / REJECT
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
                "ℹ️ Заявка уже обработана."
            )
            return

        accepted = data.startswith("app_accept_")

        status = (
            "accepted"
            if accepted
            else "rejected"
        )

        conn = db_connect()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE applications
            SET status = ?
            WHERE id = ?
            """,
            (status, app_id)
        )

        conn.commit()
        conn.close()

        if accepted:

            admin_text = "🟢 Заявка принята."

            user_text = (
                "🎉 <b>Поздравляем!</b>\n\n"
                "Твоя заявка в REWET HOST принята!"
            )

        else:

            admin_text = "🔴 Заявка отклонена."

            user_text = (
                "❌ <b>Заявка отклонена.</b>\n\n"
                "К сожалению, заявка не была принята."
            )

        await query.edit_message_text(
            admin_text,
            parse_mode="HTML"
        )

        try:
            await context.bot.send_message(
                application[1],
                user_text,
                parse_mode="HTML"
            )
        except Exception:
            pass

        return


# =========================================================
# GROUP HELPERS
# =========================================================

def is_group(update):
    chat = update.effective_chat

    return (
        chat
        and chat.type in ("group", "supergroup")
    )


def user_mention(user):
    name = html.escape(
        user.first_name or "Пользователь"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}</a>'
    )


def is_bot_mentioned(update, context):

    message = update.message

    if not message or not message.text:
        return False

    text = message.text.lower()

    if "rewet" in text or "ревет" in text:
        return True

    if BOT_USERNAME:

        pattern = rf"@{re.escape(BOT_USERNAME)}\b"

        if re.search(
            pattern,
            message.text,
            flags=re.IGNORECASE
        ):
            return True

    return False


def is_reply_to_bot(update, context):

    message = update.message

    if not message:
        return False

    if not message.reply_to_message:
        return False

    if not message.reply_to_message.from_user:
        return False

    return (
        message.reply_to_message.from_user.id
        == context.bot.id
    )


def check_group_cooldown(user_id):

    now = datetime.now().timestamp()

    last = group_cooldowns.get(
        user_id,
        0
    )

    if now - last < GROUP_COOLDOWN:
        return False

    group_cooldowns[user_id] = now

    return True


# =========================================================
# ERROR DETECTOR
# =========================================================

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


# =========================================================
# ANTI LINK
# =========================================================

def contains_link(message):

    if not message:
        return False

    text = message.text or message.caption or ""

    pattern = (
        r"(https?://\S+|"
        r"www\.\S+|"
        r"t\.me/\S+|"
        r"telegram\.me/\S+|"
        r"discord\.gg/\S+)"
    )

    if re.search(
        pattern,
        text,
        flags=re.IGNORECASE
    ):
        return True

    entities = (
        message.entities
        or message.caption_entities
        or []
    )

    for entity in entities:

        if entity.type in (
            "url",
            "text_link"
        ):
            return True

    return False


async def anti_link_handler(update, context):

    if not is_group(update):
        return

    message = update.effective_message

    if not message:
        return

    user = update.effective_user

    if not user:
        return

    if not contains_link(message):
        return

    # Администраторы могут отправлять ссылки
    try:
        member = await context.bot.get_chat_member(
            message.chat_id,
            user.id
        )

        if member.status in (
            "administrator",
            "creator"
        ):
            return

    except Exception:
        pass

    if user.id == ADMIN_ID:
        return

    try:
        await message.delete()

        warning = await context.bot.send_message(
            message.chat_id,
            f"⚠️ {html.escape(user.first_name or 'Пользователь')}, "
            "ссылки в этом чате запрещены."
        )

        asyncio.create_task(
            delete_later(
                context.bot,
                warning.chat_id,
                warning.message_id,
                5
            )
        )

    except Exception:
        logger.exception(
            "Anti-link error"
        )


async def delete_later(
    bot,
    chat_id,
    message_id,
    seconds
):

    await asyncio.sleep(seconds)

    try:
        await bot.delete_message(
            chat_id,
            message_id
        )
    except Exception:
        pass


# =========================================================
# ANTI MAT
# =========================================================

def contains_bad_word(text):

    lowered = text.lower()

    for word in BAD_WORDS:

        if word in lowered:
            return True

    return False


async def anti_mat_handler(update, context):

    if not is_group(update):
        return

    message = update.effective_message

    if not message:
        return

    if not message.text:
        return

    user = update.effective_user

    if not user:
        return

    if user.id == ADMIN_ID:
        return

    if is_admin(user.id):
        return

    if contains_bad_word(message.text):

        try:
            await message.delete()

            count = add_warn(
                message.chat_id,
                user.id
            )

            warning = await context.bot.send_message(
                message.chat_id,
                f"⚠️ {html.escape(user.first_name or 'Пользователь')}, "
                "мат в чате запрещён.\n"
                f"Предупреждений: {count}/{MAX_WARNINGS}"
            )

            asyncio.create_task(
                delete_later(
                    context.bot,
                    warning.chat_id,
                    warning.message_id,
                    5
                )
            )

            if count >= MAX_WARNINGS:

                await context.bot.restrict_chat_member(
                    message.chat_id,
                    user.id,
                    permissions=ChatPermissions(
                        can_send_messages=False
                    ),
                    until_date=datetime.now()
                    + timedelta(hours=1)
                )

        except Exception:
            logger.exception(
                "Anti-mat error"
            )


# =========================================================
# ANTISPAM
# =========================================================

async def anti_spam_handler(update, context):

    if not is_group(update):
        return

    message = update.effective_message

    if not message or not message.text:
        return

    user = update.effective_user

    if not user:
        return

    if user.id == ADMIN_ID or is_admin(user.id):
        return

    key = (
        message.chat_id,
        user.id
    )

    now = datetime.now().timestamp()

    data = spam_data.get(
        key,
        {
            "times": [],
            "last_text": "",
            "repeat": 0,
        }
    )

    data["times"] = [
        t for t in data["times"]
        if now - t < 5
    ]

    data["times"].append(now)

    if (
        data["last_text"]
        and data["last_text"].lower()
        == message.text.lower()
    ):
        data["repeat"] += 1
    else:
        data["repeat"] = 0

    data["last_text"] = message.text

    spam_data[key] = data

    if (
        len(data["times"]) >= 6
        or data["repeat"] >= 3
    ):

        try:
            await message.delete()

            await context.bot.restrict_chat_member(
                message.chat_id,
                user.id,
                permissions=ChatPermissions(
                    can_send_messages=False
                ),
                until_date=datetime.now()
                + timedelta(minutes=5)
            )

            warning = await context.bot.send_message(
                message.chat_id,
                f"🔇 {html.escape(user.first_name or 'Пользователь')}, "
                "автоматический мут на 5 минут за спам."
            )

            asyncio.create_task(
                delete_later(
                    context.bot,
                    warning.chat_id,
                    warning.message_id,
                    5
                )
            )

            data["times"] = []
            data["repeat"] = 0

        except Exception:
            logger.exception(
                "Anti-spam error"
            )


# =========================================================
# ACTIVITY
# =========================================================

async def activity_handler(update, context):

    if not is_group(update):
        return

    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    if user.is_bot:
        return

    add_activity(
        message.chat_id,
        user.id,
        1
    )


# =========================================================
# ОБЩЕНИЕ REWET
# =========================================================

async def group_message_handler(update, context):

    if not is_group(update):
        return

    message = update.message

    if not message or not message.text:
        return

    user = update.effective_user

    if not user:
        return

    mentioned = is_bot_mentioned(
        update,
        context
    )

    replied = is_reply_to_bot(
        update,
        context
    )

    if not mentioned and not replied:
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

    text = re.sub(
        r"^(rewet|ревет)\s*[,!:.-]?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    lowered = text.lower()

    # ---------------------------------------------
    # КТО ЛОХ
    # ---------------------------------------------

    if "кто лох" in lowered:

        replied_user = None

        if message.reply_to_message:
            replied_user = (
                message.reply_to_message.from_user
            )

        if replied_user and not replied_user.is_bot:

            await message.reply_text(
                "😂 Сегодня лох дня — "
                f"{user_mention(replied_user)} 😎",
                parse_mode="HTML"
            )

        else:

            await message.reply_text(
                "😂 Лох дня пока не найден.\n\n"
                "Ответь на сообщение человека и напиши:\n"
                "<b>REWET, кто лох?</b>",
                parse_mode="HTML"
            )

        return

    # ---------------------------------------------
    # ПОВЫСЬ
    # ---------------------------------------------

    if (
        user.id == ADMIN_ID
        and (
            "повысь" in lowered
            or "сделай админом" in lowered
            or "дай админку" in lowered
        )
    ):

        target = None

        if message.reply_to_message:
            target = (
                message.reply_to_message.from_user
            )

        if target:

            try:

                await promote_user(
                    message.chat_id,
                    target.id,
                    context.bot
                )

                await message.reply_text(
                    f"👑 {user_mention(target)} "
                    "теперь администратор чата!",
                    parse_mode="HTML"
                )

            except Exception:

                await message.reply_text(
                    "❌ Не смог повысить. "
                    "Проверь права бота."
                )

        else:

            await message.reply_text(
                "👑 Ответь на сообщение пользователя "
                "и напиши: REWET, повысь его."
            )

        return

    # ---------------------------------------------
    # ПРИВЕТ
    # ---------------------------------------------

    if (
        "привет" in lowered
        or lowered in (
            "ку",
            "хай",
            "здарова",
            "добрый день",
            "добрый вечер"
        )
    ):

        await message.reply_text(
            f"👋 Привет, "
            f"{html.escape(user.first_name or 'друг')}!"
        )

        return

    # ---------------------------------------------
    # КАК ДЕЛА
    # ---------------------------------------------

    if "как дела" in lowered:

        await message.reply_text(
            "😎 Всё отлично! REWET HOST работает "
            "и следит за чатом."
        )

        return

    # ---------------------------------------------
    # ПОМОГИ
    # ---------------------------------------------

    if (
        "помоги" in lowered
        or "помощь" in lowered
    ):

        await message.reply_text(
            "🛠️ Конечно!\n\n"
            "Напиши проблему или ошибку.\n"
            "Если это Pawn/SA-MP — отправь полный текст ошибки."
        )

        return

    # ---------------------------------------------
    # КТО ТЫ
    # ---------------------------------------------

    if (
        "кто ты" in lowered
        or "ты кто" in lowered
    ):

        await message.reply_text(
            "🤖 Я REWET — бот чата REWET HOST.\n\n"
            "Могу модерировать чат, "
            "помогать с командами и отвечать пользователям."
        )

        return

    # ---------------------------------------------
    # ЧТО УМЕЕШЬ
    # ---------------------------------------------

    if (
        "что умеешь" in lowered
        or "что ты умеешь" in lowered
    ):

        await message.reply_text(
            "😎 Много чего:\n\n"
            "🛡️ Модерация\n"
            "🔗 Анти-ссылки\n"
            "🚫 Анти-мат\n"
            "⚠️ Варны\n"
            "🔇 Муты\n"
            "🔨 Баны\n"
            "👑 Админка\n"
            "🏆 Рейтинг\n"
            "🎁 Розыгрыши\n"
            "💬 Общение"
        )

        return

    # ---------------------------------------------
    # СПАСИБО
    # ---------------------------------------------

    if "спасибо" in lowered:

        await message.reply_text(
            "😎 Не за что!"
        )

        return

    # ---------------------------------------------
    # ОШИБКИ
    # ---------------------------------------------

    error = detect_error(text)

    if error:

        await message.reply_text(
            f"🛠️ Найдена ошибка "
            f"<b>{html.escape(error)}</b>.\n\n"
            "Пришли полный текст ошибки или скриншот.",
            parse_mode="HTML"
        )

        return

    # ---------------------------------------------
    # ОБЩИЙ ОТВЕТ
    # ---------------------------------------------

    await message.reply_text(
        "💬 Я тебя услышал 😎\n\n"
        "Напиши подробнее, что нужно сделать."
    )


# =========================================================
# APPLICATION TEXT
# =========================================================

async def application_text_handler(update, context):

    if is_group(update):
        return

    user = update.effective_user

    if not user or not update.message:
        return

    if "application_question" not in context.user_data:
        return

    text = update.message.text.strip()

    if not text:
        return

    if len(text) > 1500:

        await update.message.reply_text(
            "❌ Максимум 1500 символов."
        )

        return

    answers = context.user_data.get(
        "application_answers",
        []
    )

    question = context.user_data[
        "application_question"
    ]

    answers.append(text)

    if question + 1 < len(APPLICATION_QUESTIONS):

        context.user_data["application_answers"] = answers

        context.user_data[
            "application_question"
        ] = question + 1

        await update.message.reply_text(
            f"📝 <b>Вопрос {question + 2} "
            f"из {len(APPLICATION_QUESTIONS)}</b>\n\n"
            f"<b>{APPLICATION_QUESTIONS[question + 1]}</b>",
            parse_mode="HTML"
        )

        return

    context.user_data[
        "application_answers"
    ] = answers

    result = "📋 <b>Проверь заявку:</b>\n\n"

    for i, answer in enumerate(answers):

        result += (
            f"<b>{i + 1}. "
            f"{html.escape(APPLICATION_QUESTIONS[i])}</b>\n"
            f"{html.escape(answer)}\n\n"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Отправить",
                callback_data="application_send"
            ),
            InlineKeyboardButton(
                "❌ Отменить",
                callback_data="application_cancel"
            )
        ]
    ])

    await update.message.reply_text(
        result,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# POST INIT
# =========================================================

async def post_init(application):

    global BOT_USERNAME

    me = await application.bot.get_me()

    BOT_USERNAME = me.username or ""

    logger.info(
        "REWET HOST BOT: @%s",
        BOT_USERNAME
    )


# =========================================================
# ERROR
# =========================================================

async def error_handler(update, context):

    logger.exception(
        "Ошибка update:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не найден."
        )

    init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # -----------------------------------------------------
    # ОСНОВНЫЕ КОМАНДЫ
    # -----------------------------------------------------

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("errors", errors_command))
    app.add_handler(CommandHandler("chat", chat_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # -----------------------------------------------------
    # АДМИНКА БОТА
    # -----------------------------------------------------

    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("applications", stats_command))
    app.add_handler(CommandHandler("setadmin", setadmin_command))
    app.add_handler(CommandHandler("deladmin", deladmin_command))
    app.add_handler(CommandHandler("admins", admins_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # -----------------------------------------------------
    # TELEGRAM АДМИНКА
    # -----------------------------------------------------

    app.add_handler(CommandHandler("promote", promote_command))
    app.add_handler(CommandHandler("demote", demote_command))

    # -----------------------------------------------------
    # МОДЕРАЦИЯ
    # -----------------------------------------------------

    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("unwarn", unwarn_command))
    app.add_handler(CommandHandler("warns", warns_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("userinfo", userinfo_command))

    # -----------------------------------------------------
    # РЕЙТИНГ / РОЗЫГРЫШ
    # -----------------------------------------------------

    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("giveaway", giveaway_command))

    # -----------------------------------------------------
    # НОВЫЕ УЧАСТНИКИ
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            new_member_handler
        )
    )

    # -----------------------------------------------------
    # CALLBACK
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    # -----------------------------------------------------
    # МОДЕРАЦИЯ СООБЩЕНИЙ
    # Используем отдельные группы, чтобы обработчики
    # не мешали друг другу.
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.ALL,
            anti_link_handler
        ),
        group=-4
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            anti_mat_handler
        ),
        group=-3
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            anti_spam_handler
        ),
        group=-2
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            activity_handler
        ),
        group=-1
    )

    # -----------------------------------------------------
    # ЗАЯВКИ
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            application_text_handler
        ),
        group=0
    )

    # -----------------------------------------------------
    # ОБЩЕНИЕ REWET
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            group_message_handler
        ),
        group=1
    )

    app.add_error_handler(error_handler)

    logger.info(
        "🚀 REWET HOST BOT запускается..."
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
