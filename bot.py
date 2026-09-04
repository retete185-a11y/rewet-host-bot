import os
import re
import sqlite3
import logging
import html
import random
import asyncio
from datetime import datetime

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

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO admins
        (user_id, added_by, added_at)
        VALUES (?, ?, ?)
        """,
        (
            ADMIN_ID,
            ADMIN_ID,
            datetime.now().isoformat(),
        ),
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
        datetime.now().isoformat(),
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
        (user_id,),
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
            datetime.now().isoformat(),
        ),
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
        (user_id,),
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
            InlineKeyboardButton(
                "📝 Подать заявку",
                callback_data="apply",
            )
        ],
        [
            InlineKeyboardButton(
                "👤 Профиль",
                callback_data="profile",
            ),
            InlineKeyboardButton(
                "📋 Моя заявка",
                callback_data="my_application",
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 О проекте",
                callback_data="about",
            ),
            InlineKeyboardButton(
                "💬 Поддержка",
                callback_data="support",
            ),
        ],
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📋 Заявки",
                callback_data="admin_apps",
            ),
            InlineKeyboardButton(
                "📊 Статистика",
                callback_data="admin_stats",
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 Пользователи",
                callback_data="admin_users",
            ),
            InlineKeyboardButton(
                "👮 Админы",
                callback_data="admin_admins",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 Главное меню",
                callback_data="back_main",
            )
        ],
    ])


def subscription_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Подписаться на канал",
                url=CHANNEL_URL,
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Я подписался",
                callback_data="check_subscription",
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
        reply_markup=main_menu(),
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

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
            "\n👮 <b>Админ-команды бота:</b>\n"
            "/admin — админ-панель\n"
            "/setadmin ID — выдать админку бота\n"
            "/deladmin ID — снять админку бота\n"
            "/admins — список админов бота\n"
            "/stats — статистика\n"
            "/applications — заявки\n\n"

            "👑 <b>Админ-команды Telegram-чата:</b>\n"
            "/promote ID — повысить в чате\n"
            "/demote ID — снять админку чата\n\n"

            "Можно также ответить на сообщение пользователя:\n"
            "/promote\n"
            "/demote"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_command(update, context)


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            f"💬 Поддержка REWET HOST:\n{SUPPORT_USERNAME}"
        )


async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    await update.message.reply_text(
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
        "🔴 server.exe / crashdetect",
        parse_mode="HTML",
    )


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    await update.message.reply_text(
        "💬 <b>REWET HOST CHAT</b>\n\n"
        "Обратись ко мне так:\n"
        "• <b>REWET, помоги</b>\n"
        "• <b>REWET, как дела?</b>\n"
        "• <b>REWET, кто лох?</b>\n"
        "• или ответь на сообщение бота.\n\n"
        "🧹 Ссылки в чате удаляются автоматически.\n"
        "🔒 Новые участники сначала должны подписаться на @rewethost.",
        parse_mode="HTML",
    )


# =========================================================
# АДМИНКА БОТА
# =========================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message:
        return

    if not user or not is_admin(user.id):
        await update.message.reply_text(
            "❌ У тебя нет доступа к админ-панели."
        )
        return

    await update.message.reply_text(
        "👮 <b>Админ-панель REWET HOST</b>",
        parse_mode="HTML",
        reply_markup=admin_menu(),
    )


async def setadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message:
        return

    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Только главный администратор может выдавать админку бота."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❗ Использование:\n/setadmin ID"
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
            "ℹ️ Это главный администратор."
        )
        return

    if add_admin(target_id, user.id):
        await update.message.reply_text(
            f"✅ <code>{target_id}</code> получил админку бота.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"ℹ️ <code>{target_id}</code> уже является админом бота.",
            parse_mode="HTML",
        )


async def deladmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message:
        return

    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Только главный администратор может снимать админку бота."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❗ Использование:\n/deladmin ID"
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
            "❌ Нельзя снять админку главного администратора."
        )
        return

    if remove_admin(target_id):
        await update.message.reply_text(
            f"✅ Админка бота <code>{target_id}</code> снята.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "ℹ️ Такой админ не найден."
        )


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message:
        return

    if not user or not is_admin(user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return

    admins = get_admins()

    text = "👮 <b>Администраторы REWET HOST</b>\n\n"

    for admin in admins:
        role = (
            "👑 Главный"
            if admin[0] == ADMIN_ID
            else "🛡 Администратор"
        )

        text += (
            f"{role}: <code>{admin[0]}</code>\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# =========================================================
# TELEGRAM-АДМИНКА
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
            return None

    return None


async def promote_user(update, context, target_id):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in ("group", "supergroup"):
        await message.reply_text(
            "❌ Повышать пользователей можно только в группе."
        )
        return

    if target_id == context.bot.id:
        await message.reply_text(
            "❌ Я уже администратор."
        )
        return

    try:
        member = await context.bot.get_chat_member(
            chat.id,
            target_id,
        )

        if member.status == "creator":
            await message.reply_text(
                "❌ Пользователь уже создатель группы."
            )
            return

        await context.bot.promote_chat_member(
            chat_id=chat.id,
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

        await message.reply_text(
            f"👑 Пользователь <code>{target_id}</code> "
            "теперь администратор Telegram-чата.",
            parse_mode="HTML",
        )

    except Exception:
        logger.exception("Ошибка promote")

        await message.reply_text(
            "❌ Не получилось повысить пользователя.\n\n"
            "Проверь, что бот сам является администратором "
            "и имеет право <b>добавлять новых администраторов</b>.",
            parse_mode="HTML",
        )


async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "❌ Только главный администратор может повышать людей в чате."
        )
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await update.effective_message.reply_text(
            "❗ Ответь на сообщение пользователя командой:\n"
            "/promote\n\n"
            "или:\n"
            "/promote ID"
        )
        return

    await promote_user(
        update,
        context,
        target_id,
    )


async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    if not user or not message or not chat:
        return

    if user.id != ADMIN_ID:
        await message.reply_text(
            "❌ Только главный администратор может снимать админку чата."
        )
        return

    target_id = get_target_user_id(update, context)

    if not target_id:
        await message.reply_text(
            "❗ Ответь на сообщение пользователя командой:\n"
            "/demote\n\n"
            "или:\n"
            "/demote ID"
        )
        return

    if target_id == ADMIN_ID:
        await message.reply_text(
            "❌ Нельзя снять права главного администратора REWET HOST."
        )
        return

    try:
        member = await context.bot.get_chat_member(
            chat.id,
            target_id,
        )

        if member.status == "creator":
            await message.reply_text(
                "❌ Нельзя снять права создателя группы."
            )
            return

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
            f"✅ Админка пользователя <code>{target_id}</code> снята.",
            parse_mode="HTML",
        )

    except Exception:
        logger.exception("Ошибка demote")

        await message.reply_text(
            "❌ Не удалось снять админку."
        )


# =========================================================
# СТАТИСТИКА
# =========================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message:
        return

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

    conn.close()

    await update.message.reply_text(
        "📊 <b>Статистика REWET HOST</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📋 Заявок: <b>{applications}</b>\n"
        f"🟡 Ожидают: <b>{pending}</b>\n"
        f"🟢 Принято: <b>{accepted}</b>\n"
        f"🔴 Отклонено: <b>{rejected}</b>",
        parse_mode="HTML",
    )


# =========================================================
# ЗАЯВКА
# =========================================================

async def start_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    existing = get_pending_application(user.id)

    if existing:
        await update.effective_message.reply_text(
            "⏳ У тебя уже есть заявка на рассмотрении."
        )
        return

    context.user_data["application_question"] = 0
    context.user_data["application_answers"] = []

    await update.effective_message.reply_text(
        f"📝 <b>Заявка в REWET HOST</b>\n\n"
        f"Вопрос 1 из {len(APPLICATION_QUESTIONS)}\n\n"
        f"<b>{APPLICATION_QUESTIONS[0]}</b>\n\n"
        "Напиши ответ сообщением.",
        parse_mode="HTML",
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("application_question", None)
    context.user_data.pop("application_answers", None)

    if update.message:
        await update.message.reply_text(
            "❌ Заявка отменена."
        )


async def application_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
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
            "❌ Максимум 1500 символов."
        )
        return

    answers = context.user_data.get(
        "application_answers",
        [],
    )

    question_index = context.user_data[
        "application_question"
    ]

    answers.append(text)

    if question_index + 1 < len(APPLICATION_QUESTIONS):
        context.user_data["application_answers"] = answers
        context.user_data["application_question"] = question_index + 1

        await update.message.reply_text(
            f"📝 <b>Вопрос {question_index + 2} "
            f"из {len(APPLICATION_QUESTIONS)}</b>\n\n"
            f"<b>{APPLICATION_QUESTIONS[question_index + 1]}</b>",
            parse_mode="HTML",
        )
        return

    context.user_data["application_answers"] = answers

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
                callback_data="application_send",
            ),
            InlineKeyboardButton(
                "❌ Отменить",
                callback_data="application_cancel",
            ),
        ]
    ])

    await update.message.reply_text(
        result + "Отправить заявку?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def send_application(update, context):
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
        datetime.now().isoformat(),
    ))

    app_id = cur.lastrowid

    conn.commit()
    conn.close()

    context.user_data.pop("application_question", None)
    context.user_data.pop("application_answers", None)

    await query.edit_message_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Ожидай решения администрации REWET HOST.",
        parse_mode="HTML",
    )

    application_text = (
        f"📋 <b>Новая заявка #{app_id}</b>\n\n"
        f"👤 {html.escape(user.first_name or '')}\n"
        f"🆔 <code>{user.id}</code>\n"
        f"🔗 @{html.escape(user.username or 'нет')}\n\n"
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
                callback_data=f"app_accept_{app_id}",
            ),
            InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"app_reject_{app_id}",
            ),
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=application_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Ошибка отправки заявки админу")


# =========================================================
# ПОДПИСКА
# =========================================================

async def check_subscription(user_id, bot):
    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id,
        )

        return (
            member.status in (
                "member",
                "administrator",
                "creator",
            )
            or getattr(member, "is_member", False)
        )

    except Exception:
        logger.exception("Ошибка проверки подписки")
        return False


async def restrict_user_in_chat(chat_id, user_id, bot):
    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=False,
        ),
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
        ),
    )


# =========================================================
# НОВЫЙ УЧАСТНИК
# =========================================================

async def new_member_handler(update, context):
    message = update.message

    if not message:
        return

    chat = update.effective_chat

    if not chat or chat.type not in ("group", "supergroup"):
        return

    for new_user in message.new_chat_members:

        if new_user.is_bot:
            continue

        register_user(new_user)

        try:
            await restrict_user_in_chat(
                chat.id,
                new_user.id,
                context.bot,
            )
        except Exception:
            logger.exception(
                "Не удалось ограничить нового участника"
            )

        name = html.escape(
            new_user.first_name or "друг"
        )

        text = (
            f"👋 <b>Привет, {name}!</b>\n\n"
            "Добро пожаловать в <b>REWET HOST</b>! 🚀\n\n"
            "🔒 Чтобы писать в чат, сначала "
            "подпишись на наш канал:\n"
            "<b>@rewethost</b>\n\n"
            "После подписки нажми "
            "«✅ Я подписался»."
        )

        try:
            await message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=subscription_keyboard(),
            )
        except Exception:
            logger.exception(
                "Не удалось отправить приветствие"
            )


# =========================================================
# CALLBACK
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

        if not chat or chat.type not in ("group", "supergroup"):
            await query.answer(
                "❌ Проверять подписку нужно в группе.",
                show_alert=True,
            )
            return

        subscribed = await check_subscription(
            user.id,
            context.bot,
        )

        if not subscribed:
            await query.answer(
                "❌ Подписка не найдена. Подпишись на @rewethost.",
                show_alert=True,
            )
            return

        try:
            await unrestrict_user_in_chat(
                chat.id,
                user.id,
                context.bot,
            )
        except Exception:
            logger.exception("Ошибка снятия ограничения")

            await query.answer(
                "❌ Бот не может открыть доступ. "
                "Проверь права бота.",
                show_alert=True,
            )
            return

        try:
            await query.edit_message_text(
                f"🎉 <b>{html.escape(user.first_name or 'Друг')}</b>, "
                "подписка подтверждена!\n\n"
                "🔓 Теперь тебе разрешено писать в чат.\n"
                "Добро пожаловать в REWET HOST! 🚀",
                parse_mode="HTML",
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # МЕНЮ
    # -----------------------------------------------------

    if data == "apply":
        await start_application(update, context)
        return

    if data == "application_send":
        await send_application(update, context)
        return

    if data == "application_cancel":

        context.user_data.pop(
            "application_question",
            None,
        )

        context.user_data.pop(
            "application_answers",
            None,
        )

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
            f"👮 Администратор бота: "
            f"{'Да' if is_admin(user.id) else 'Нет'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="back_main",
                    )
                ]
            ]),
        )
        return

    if data == "my_application":

        application = get_pending_application(user.id)

        if not application:
            await query.edit_message_text(
                "📋 У тебя нет заявки на рассмотрении.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 Назад",
                            callback_data="back_main",
                        )
                    ]
                ]),
            )
            return

        await query.edit_message_text(
            f"📋 <b>Твоя заявка</b>\n\n"
            f"Номер: <code>#{application[0]}</code>\n"
            f"Статус: 🟡 На рассмотрении\n"
            f"Дата: {html.escape(application[4])}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="back_main",
                    )
                ]
            ]),
        )
        return

    if data == "about":

        await query.edit_message_text(
            "📢 <b>REWET HOST</b>\n\n"
            "Игровой хостинг и проект для игроков "
            "и разработчиков.\n\n"
            "🚀 Развитие\n"
            "🛠️ Поддержка\n"
            "🎮 Игровые серверы\n"
            "👥 Команда проекта",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="back_main",
                    )
                ]
            ]),
        )
        return

    if data == "support":

        await query.edit_message_text(
            f"💬 <b>Поддержка</b>\n\n{SUPPORT_USERNAME}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Назад",
                        callback_data="back_main",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # АДМИНКА
    # -----------------------------------------------------

    if data.startswith("admin_") and not is_admin(user.id):
        await query.edit_message_text(
            "❌ У тебя нет доступа."
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
                    "rejected": "🔴",
                }.get(app[3], "⚪")

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
                        callback_data="admin_back",
                    )
                ]
            ]),
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
                [
                    InlineKeyboardButton(
                        "🔙 Админ-панель",
                        callback_data="admin_back",
                    )
                ]
            ]),
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
            f"Всего: <b>{users}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Админ-панель",
                        callback_data="admin_back",
                    )
                ]
            ]),
        )
        return

    if data == "admin_admins":

        admins = get_admins()

        text = "👮 <b>Администраторы</b>\n\n"

        for admin in admins:
            role = (
                "👑 Главный"
                if admin[0] == ADMIN_ID
                else "🛡 Админ"
            )

            text += (
                f"{role}: <code>{admin[0]}</code>\n"
            )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Админ-панель",
                        callback_data="admin_back",
                    )
                ]
            ]),
        )
        return

    if data == "admin_back":

        await query.edit_message_text(
            "👮 <b>Админ-панель REWET HOST</b>",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return

    if data == "back_main":

        await query.edit_message_text(
            "🚀 <b>REWET HOST</b>\n\nГлавное меню:",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return

    # -----------------------------------------------------
    # ЗАЯВКИ ACCEPT / REJECT
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

        new_status = (
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
            (new_status, app_id),
        )

        conn.commit()
        conn.close()

        if accepted:
            status_text = "🟢 Заявка принята!"
            user_text = (
                "🎉 <b>Поздравляем!</b>\n\n"
                "Твоя заявка в команду REWET HOST "
                "была <b>принята</b>."
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
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=application[1],
                text=user_text,
                parse_mode="HTML",
            )
        except Exception:
            pass

        return


# =========================================================
# GROUP
# =========================================================

def is_group(update):
    chat = update.effective_chat

    return bool(
        chat and chat.type in (
            "group",
            "supergroup",
        )
    )


def is_bot_mentioned(update, context):
    message = update.message

    if not message or not message.text:
        return False

    text = message.text.strip()

    # @username
    if BOT_USERNAME:
        if re.search(
            rf"@{re.escape(BOT_USERNAME)}\b",
            text,
            flags=re.IGNORECASE,
        ):
            return True

    # REWET / РЕВЕТ
    if re.match(
        r"^\s*(rewet|ревет)\b",
        text,
        flags=re.IGNORECASE,
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
        0,
    )

    if now - last < GROUP_COOLDOWN:
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


def clean_bot_call(text):
    if not text:
        return ""

    if BOT_USERNAME:
        text = re.sub(
            rf"@{re.escape(BOT_USERNAME)}\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(
        r"^\s*(rewet|ревет)\b[:,!\s-]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


# =========================================================
# АНТИССЫЛКИ
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
        r"discord\.gg/\S+|"
        r"discord\.com/invite/\S+)"
    )

    if re.search(
        pattern,
        text,
        flags=re.IGNORECASE,
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
            "text_link",
        ):
            return True

    return False


async def delete_later(
    bot,
    chat_id,
    message_id,
    seconds,
):
    await asyncio.sleep(seconds)

    try:
        await bot.delete_message(
            chat_id,
            message_id,
        )
    except Exception:
        pass


async def anti_link_handler(update, context):

    if not is_group(update):
        return

    message = update.effective_message

    if not message:
        return

    user = update.effective_user

    if not user:
        return

    # Команды и обычные сообщения без текста/ссылки
    if not contains_link(message):
        return

    # Главный админ и админы чата могут отправлять ссылки
    if user.id == ADMIN_ID:
        return

    try:
        member = await context.bot.get_chat_member(
            message.chat_id,
            user.id,
        )

        if member.status in (
            "administrator",
            "creator",
        ):
            return

    except Exception:
        pass

    try:
        await message.delete()

        warning = await context.bot.send_message(
            chat_id=message.chat_id,
            text=(
                f"🚫 {html.escape(user.first_name or 'Пользователь')}, "
                "ссылки в этом чате запрещены."
            ),
            parse_mode="HTML",
        )

        context.application.create_task(
            delete_later(
                context.bot,
                warning.chat_id,
                warning.message_id,
                5,
            )
        )

    except Exception:
        logger.exception(
            "Ошибка анти-ссылок"
        )


# =========================================================
# ОБЩЕНИЕ REWET
# =========================================================

def user_mention(user):
    name = html.escape(
        user.full_name
        or user.first_name
        or "пользователь"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}'
        f'</a>'
    )


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
        context,
    )

    replied = is_reply_to_bot(
        update,
        context,
    )

    if not mentioned and not replied:
        return

    if not check_group_cooldown(user.id):
        return

    text = clean_bot_call(
        message.text
    )

    lowered = text.lower().strip()

    # =====================================================
    # ПОВЫШЕНИЕ ЧЕРЕЗ ОБЩЕНИЕ
    # =====================================================

    if user.id == ADMIN_ID:

        promote_words = (
            "повысь",
            "сделай админом",
            "дай админку",
            "назначь админом",
        )

        if any(word in lowered for word in promote_words):

            target = None

            if message.reply_to_message:
                target = message.reply_to_message.from_user

            if target:
                await promote_user(
                    update,
                    context,
                    target.id,
                )
                return

            await message.reply_text(
                "👑 Ответь на сообщение человека и напиши:\n"
                "<b>REWET, повысь</b>",
                parse_mode="HTML",
            )
            return

    # =====================================================
    # КТО ЛОХ
    # =====================================================

    if (
        "кто лох" in lowered
        or "кто лох?" in lowered
    ):

        target = None

        if message.reply_to_message:
            target = message.reply_to_message.from_user

        if target and not target.is_bot:

            answers = [
                f"😂 Сегодня лох дня — {user_mention(target)}!",
                f"🤣 REWET вынес вердикт: {user_mention(target)}!",
                f"😎 Кажется, ответ найден — {user_mention(target)}.",
                f"😂 Не буду сдавать, но сообщение выше выглядит подозрительно 👀",
            ]

            await message.reply_text(
                random.choice(answers),
                parse_mode="HTML",
            )
        else:
            await message.reply_text(
                "😂 Ответь на сообщение человека и спроси "
                "<b>REWET, кто лох?</b> — тогда разберёмся 😎",
                parse_mode="HTML",
            )

        return

    # =====================================================
    # ПРИВЕТ
    # =====================================================

    if (
        "привет" in lowered
        or lowered in ("ку", "хай", "здарова")
    ):
        await message.reply_text(
            f"👋 Привет, "
            f"{html.escape(user.first_name or 'друг')}!"
        )
        return

    # =====================================================
    # КАК ДЕЛА
    # =====================================================

    if "как дела" in lowered:

        await message.reply_text(
            "😎 Всё отлично! REWET HOST работает."
        )
        return

    # =====================================================
    # ПОМОГИ
    # =====================================================

    if (
        "помоги" in lowered
        or "помощь" in lowered
    ):
        await message.reply_text(
            "🛠️ Конечно! Скинь проблему, ошибку "
            "или объясни, что случилось."
        )
        return

    # =====================================================
    # КТО ТЫ
    # =====================================================

    if "кто ты" in lowered:

        await message.reply_text(
            "🤖 Я REWET — бот чата REWET HOST!"
        )
        return

    # =====================================================
    # ЧТО УМЕЕШЬ
    # =====================================================

    if (
        "что умеешь" in lowered
        or "что ты умеешь" in lowered
    ):
        await message.reply_text(
            "🤖 Я умею:\n\n"
            "🛠️ помогать с ошибками;\n"
            "🗣️ общаться в чате;\n"
            "🧹 удалять ссылки;\n"
            "🔒 проверять подписку;\n"
            "👮 управлять участниками;\n"
            "📋 работать с заявками."
        )
        return

    # =====================================================
    # СПАСИБО
    # =====================================================

    if "спасибо" in lowered:

        await message.reply_text(
            "😎 Не за что!"
        )
        return

    # =====================================================
    # ОШИБКИ
    # =====================================================

    error = detect_error(text)

    if error:

        await message.reply_text(
            f"🛠️ Похоже, у тебя ошибка "
            f"<b>{html.escape(error)}</b>.\n\n"
            "Пришли полный текст ошибки или скриншот.",
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ОБЩИЙ ОТВЕТ
    # =====================================================

    await message.reply_text(
        f"💬 {html.escape(user.first_name or 'Друг')}, "
        "я тебя услышал 😎\n\n"
        "Я пока работаю без ИИ, но уже умею "
        "отвечать на основные вопросы и команды."
    )


# =========================================================
# POST INIT
# =========================================================

async def post_init(application):

    global BOT_USERNAME

    me = await application.bot.get_me()

    BOT_USERNAME = me.username or ""

    logger.info(
        "REWET HOST BOT запущен: @%s",
        BOT_USERNAME,
    )


# =========================================================
# ERROR
# =========================================================

async def error_handler(update, context):

    logger.error(
        "Ошибка обработки update",
        exc_info=context.error,
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

    # =====================================================
    # КОМАНДЫ
    # =====================================================

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("errors", errors_command))
    app.add_handler(CommandHandler("chat", chat_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # =====================================================
    # АДМИНКА БОТА
    # =====================================================

    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("applications", stats_command))
    app.add_handler(CommandHandler("setadmin", setadmin_command))
    app.add_handler(CommandHandler("deladmin", deladmin_command))
    app.add_handler(CommandHandler("admins", admins_command))

    # =====================================================
    # АДМИНКА TELEGRAM-ЧАТА
    # =====================================================

    app.add_handler(CommandHandler("promote", promote_command))
    app.add_handler(CommandHandler("demote", demote_command))

    # =====================================================
    # НОВЫЕ УЧАСТНИКИ
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            new_member_handler,
        )
    )

    # =====================================================
    # CALLBACK
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    # =====================================================
    # АНТИССЫЛКИ
    #
    # Отдельная группа, чтобы анти-ссылки работали
    # независимо от остальных обработчиков.
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.ALL,
            anti_link_handler,
        ),
        group=1,
    )

    # =====================================================
    # ЗАЯВКИ
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            application_text_handler,
        ),
        group=2,
    )

    # =====================================================
    # ОБЩЕНИЕ
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            group_message_handler,
        ),
        group=3,
    )

    # =====================================================
    # ОШИБКИ
    # =====================================================

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "REWET HOST BOT запускается..."
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
