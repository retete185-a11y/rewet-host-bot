import os, sqlite3, ast, logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

load_dotenv()
TOKEN=os.getenv("BOT_TOKEN")
ADMIN_ID=int(os.getenv("ADMIN_ID","8999035301"))
DB="rewet_host.db"
logging.basicConfig(level=logging.INFO)

QUESTIONS=[
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

def conn():
    c=sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,username TEXT,
        status TEXT DEFAULT 'pending',data TEXT,created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,username TEXT,first_seen TEXT)""")
    c.commit(); return c

def register_user(u):
    c=conn(); c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?)",(u.id,u.username or "",datetime.now().isoformat(timespec="seconds"))); c.commit(); c.close()

def pending(uid):
    c=conn(); r=c.execute("SELECT id FROM applications WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",(uid,)).fetchone(); c.close(); return r

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Подать заявку",callback_data="apply")],
        [InlineKeyboardButton("📋 Моя заявка",callback_data="my"),InlineKeyboardButton("📢 О проекте",callback_data="about")],
        [InlineKeyboardButton("💬 Поддержка",callback_data="support")]
    ])

async def start(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    ctx.user_data.clear()
    await update.message.reply_text(
        "🔥 <b>REWET HOST</b>\n\nДобро пожаловать в официальный бот проекта!\n\n"
        "Здесь можно подать заявку в команду, узнать статус и получить помощь.",
        parse_mode="HTML",reply_markup=main_kb())

async def menu(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    register_user(q.from_user)
    if q.data=="about":
        await q.message.reply_text("🚀 <b>REWET HOST</b> — игровой хостинг нового поколения.\n⚡ Быстрый запуск\n🛡️ Надёжность\n💻 Удобная панель\n🤝 Команда проекта",parse_mode="HTML")
    elif q.data=="support":
        await q.message.reply_text("💬 По вопросам REWET HOST обратитесь к администрации проекта.")
    elif q.data=="my":
        r=pending(q.from_user.id)
        if r: await q.message.reply_text(f"📋 Ваша заявка <b>#{r[0]}</b> находится на рассмотрении.",parse_mode="HTML")
        else: await q.message.reply_text("📋 Активной заявки нет.")
    elif q.data=="apply":
        if pending(q.from_user.id):
            await q.message.reply_text("⚠️ У вас уже есть заявка на рассмотрении."); return
        ctx.user_data["answers"]=[]; ctx.user_data["step"]=0
        await q.message.reply_text("📝 <b>Заполняем анкету</b>\n\n"+QUESTIONS[0][0],parse_mode="HTML")

async def text(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if "step" not in ctx.user_data: return
    answers=ctx.user_data["answers"]
    answers.append(update.message.text.strip())
    step=ctx.user_data["step"]+1
    if step<len(QUESTIONS):
        ctx.user_data["step"]=step
        await update.message.reply_text("➡️ "+QUESTIONS[step][0])
        return
    ctx.user_data["step"]="confirm"
    labels=[x[0] for x in QUESTIONS]
    out="📋 <b>ПРОВЕРЬТЕ АНКЕТУ</b>\n\n"
    for label,val in zip(labels,answers): out+=f"<b>{label}</b>\n{val}\n\n"
    await update.message.reply_text(out,parse_mode="HTML",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить",callback_data="send"),InlineKeyboardButton("❌ Отменить",callback_data="cancel")]
    ]))

async def confirm(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="cancel":
        ctx.user_data.clear(); await q.edit_message_text("❌ Заявка отменена."); return
    if ctx.user_data.get("step")!="confirm":
        await q.message.reply_text("⚠️ Сессия заполнения устарела. Начните заново."); return
    answers=ctx.user_data["answers"]
    c=conn(); cur=c.execute("INSERT INTO applications(user_id,username,data,created_at) VALUES(?,?,?,?)",
        (q.from_user.id,q.from_user.username or "",repr(answers),datetime.now().isoformat(timespec="seconds")))
    app_id=cur.lastrowid; c.commit(); c.close()
    msg=f"📨 <b>НОВАЯ ЗАЯВКА #{app_id}</b>\n👤 ID: <code>{q.from_user.id}</code>\n"
    if q.from_user.username: msg+=f"🔗 @{q.from_user.username}\n"
    msg+="\n"
    for (label,_),val in zip(QUESTIONS,answers): msg+=f"<b>{label}</b>\n{val}\n\n"
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Принять",callback_data=f"accept:{app_id}"),InlineKeyboardButton("🔴 Отклонить",callback_data=f"reject:{app_id}")]])
    try: await ctx.bot.send_message(ADMIN_ID,msg,parse_mode="HTML",reply_markup=kb)
    except Exception: pass
    ctx.user_data.clear()
    await q.edit_message_text(f"✅ Заявка <b>#{app_id}</b> отправлена администрации.\nОжидайте решения.",parse_mode="HTML")

async def admin(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("⛔ Доступ запрещён.",show_alert=True); return
    await q.answer()
    action,raw=q.data.split(":"); app_id=int(raw)
    c=conn(); row=c.execute("SELECT user_id,status FROM applications WHERE id=?",(app_id,)).fetchone()
    if not row: await q.message.reply_text("❌ Заявка не найдена."); return
    if row[1]!="pending": await q.message.reply_text("⚠️ Заявка уже обработана."); return
    status="accepted" if action=="accept" else "rejected"
    c.execute("UPDATE applications SET status=? WHERE id=?",(status,app_id)); c.commit(); c.close()
    if status=="accepted":
        textmsg=f"🎉 <b>Ваша заявка #{app_id} одобрена!</b>\n\nДобро пожаловать в команду REWET HOST! 🔥"
        result="🟢 Заявка принята"
    else:
        textmsg=f"❌ <b>Ваша заявка #{app_id} отклонена.</b>\n\nСпасибо за участие!"
        result="🔴 Заявка отклонена"
    try: await ctx.bot.send_message(row[0],textmsg,parse_mode="HTML")
    except Exception: pass
    await q.edit_message_reply_markup(reply_markup=None)
    await q.message.reply_text(result)

async def stats(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    c=conn()
    users=c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total=c.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    pend=c.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0]
    acc=c.execute("SELECT COUNT(*) FROM applications WHERE status='accepted'").fetchone()[0]
    rej=c.execute("SELECT COUNT(*) FROM applications WHERE status='rejected'").fetchone()[0]
    c.close()
    await update.message.reply_text(f"📊 <b>REWET HOST — статистика</b>\n\n👥 Пользователей: {users}\n📨 Заявок: {total}\n⏳ На рассмотрении: {pend}\n🟢 Принято: {acc}\n🔴 Отклонено: {rej}",parse_mode="HTML")

async def apps(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID:return
    c=conn(); rows=c.execute("SELECT id,user_id,status,created_at FROM applications ORDER BY id DESC LIMIT 15").fetchall(); c.close()
    if not rows: await update.message.reply_text("📋 Заявок пока нет."); return
    s="📋 <b>Последние заявки</b>\n\n"
    for r in rows:s+=f"#{r[0]} — {r[2]} — ID {r[1]}\n"
    await update.message.reply_text(s,parse_mode="HTML")

async def cancel_cmd(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear(); await update.message.reply_text("❌ Текущая анкета сброшена.")

def main():
    if not TOKEN: raise SystemExit("BOT_TOKEN не указан в .env")
    conn().close()
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("stats",stats))
    app.add_handler(CommandHandler("applications",apps))
    app.add_handler(CommandHandler("cancel",cancel_cmd))
    app.add_handler(CallbackQueryHandler(admin,r"^(accept|reject):\d+$"))
    app.add_handler(CallbackQueryHandler(confirm,r"^(send|cancel)$"))
    app.add_handler(CallbackQueryHandler(menu,r"^(apply|my|about|support)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text))
    app.run_polling()

if __name__=="__main__": main()
