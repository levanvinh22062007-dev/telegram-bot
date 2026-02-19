import sqlite3
import random
from datetime import datetime, timedelta
from telegram import *
from telegram.ext import *
from openpyxl import Workbook

TOKEN = "8577270105:AAGgIlUMgbYmwX40zof16l05migAHiCrVhc"
SUPER_ADMIN = 7317018888

MIN_WITHDRAW = 11000
WITHDRAW_COOLDOWN_HOURS = 3

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    last_checkin TEXT,
    referrer INTEGER,
    role INTEGER DEFAULT 0,
    vip INTEGER DEFAULT 0,
    cooldown TEXT,
    referral_count INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS withdraws(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    stk TEXT,
    bank TEXT,
    name TEXT,
    amount INTEGER,
    status TEXT DEFAULT 'pending',
    time TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    time TEXT
)
""")

cursor.execute("INSERT OR IGNORE INTO users(id, role) VALUES(?,3)", (SUPER_ADMIN,))
cursor.execute("UPDATE users SET role=3 WHERE id=?", (SUPER_ADMIN,))
conn.commit()

# ================= UTIL =================
def log(user_id, action):
    cursor.execute(
        "INSERT INTO logs(user_id, action, time) VALUES(?,?,?)",
        (user_id, action, datetime.now().isoformat())
    )
    conn.commit()

def get_user(uid):
    cursor.execute("SELECT * FROM users WHERE id=?", (uid,))
    return cursor.fetchone()

def is_admin(uid):
    user = get_user(uid)
    return user and user["role"] >= 1

def is_super(uid):
    user = get_user(uid)
    return user and user["role"] >= 3

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ref = None

    if context.args:
        try:
            ref = int(context.args[0])
        except:
            pass

    user = get_user(uid)

    if not user:
        cursor.execute("INSERT INTO users(id, referrer) VALUES(?,?)", (uid, ref))
        conn.commit()

        if ref and ref != uid:
            ref_user = get_user(ref)
            if ref_user:
                bonus = 2000 if ref_user["vip"] > 0 else 1000
                cursor.execute(
                    "UPDATE users SET balance=balance+?, referral_count=referral_count+1 WHERE id=?",
                    (bonus, ref)
                )
                conn.commit()
                await context.bot.send_message(ref, f"🎉 Nhận {bonus} từ người được mời!")
                log(ref, f"Referral +{bonus}")

    keyboard = [
        ["💰 Số dư", "🎯 Điểm danh"],
        ["👥 Mời bạn bè", "💸 Rút tiền"],
        ["💎 VIP", "📊 Thống kê"]
    ]

    await update.message.reply_text(
        "🚀 hello bro vào bot 
hệ thống bot mời bạn bè kiếm tiền tiêu sau tết!",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ================= MENU =================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if not user:
        return

    text = update.message.text

    if text == "💰 Số dư":
        await update.message.reply_text(f"Số dư: {user['balance']} VND")

    elif text == "🎯 Điểm danh":
        today = datetime.now().date()

        if user["last_checkin"]:
            try:
                last = datetime.fromisoformat(user["last_checkin"]).date()
                if last == today:
                    await update.message.reply_text("Đã điểm danh hôm nay.")
                    return
            except:
                pass

        reward = random.randint(1000,2000)
        if user["vip"] > 0:
            reward *= 2

        cursor.execute(
            "UPDATE users SET balance=balance+?, last_checkin=? WHERE id=?",
            (reward, datetime.now().isoformat(), uid)
        )
        conn.commit()

        log(uid, f"Checkin +{reward}")
        await update.message.reply_text(f"+{reward} VND")

    elif text == "👥 Mời bạn bè":
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={uid}"

        await update.message.reply_text(
            f"🔗 Link mời:\n{link}\n\n"
            f"👥 Đã mời: {user['referral_count']} người"
        )

    elif text == "💎 VIP":
        await update.message.reply_text(
            "VIP 1: x2 checkin\nVIP 2: giảm cooldown rút tiền\nLiên hệ admin nâng cấp."
        )

    elif text == "💸 Rút tiền":
        await update.message.reply_text("/rutbank STK BANK TEN SOTIEN")

    elif text == "📊 Thống kê":
        if not is_admin(uid):
            return

        cursor.execute("SELECT COUNT(*) as total FROM users")
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as pending FROM withdraws WHERE status='pending'")
        pending = cursor.fetchone()["pending"]

        await update.message.reply_text(
            f"Users: {total}\nPending: {pending}"
        )

# ================= RÚT TIỀN =================
async def rutbank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if not user:
        return

    try:
        stk, bank, name, amount = context.args
        amount = int(amount)
    except:
        await update.message.reply_text("Sai cú pháp.")
        return

    if amount < MIN_WITHDRAW:
        await update.message.reply_text("Số tiền quá nhỏ.")
        return

    if user["balance"] < amount:
        await update.message.reply_text("Không đủ tiền.")
        return

    if user["cooldown"]:
        next_time = datetime.fromisoformat(user["cooldown"])
        if datetime.now() < next_time:
            await update.message.reply_text("Đang cooldown.")
            return

    cursor.execute("""
        INSERT INTO withdraws(user_id, stk, bank, name, amount, status, time)
        VALUES(?,?,?,?,?,?,?)
    """,(uid,stk,bank,name,amount,"pending",datetime.now().isoformat()))
    conn.commit()

    withdraw_id = cursor.lastrowid

    keyboard = [[
        InlineKeyboardButton("✅ Duyệt", callback_data=f"approve_{withdraw_id}"),
        InlineKeyboardButton("❌ Từ chối", callback_data=f"reject_{withdraw_id}")
    ]]

    await context.bot.send_message(
        SUPER_ADMIN,
        f"💳 RÚT TIỀN ID {withdraw_id}\nUser {uid}\n{amount} VND",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("Đã gửi admin duyệt.")
    log(uid, f"Tạo yêu cầu rút {amount}")

# ================= DUYỆT =================
async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    wid = int(query.data.split("_")[1])
    cursor.execute("SELECT * FROM withdraws WHERE id=?", (wid,))
    w = cursor.fetchone()

    if not w or w["status"] != "pending":
        return

    if query.data.startswith("approve"):
        cursor.execute("UPDATE users SET balance=balance-? WHERE id=?",(w["amount"],w["user_id"]))
        cursor.execute("UPDATE users SET cooldown=? WHERE id=?",
                       ((datetime.now()+timedelta(hours=WITHDRAW_COOLDOWN_HOURS)).isoformat(),
                        w["user_id"]))
        cursor.execute("UPDATE withdraws SET status='approved' WHERE id=?",(wid,))
        conn.commit()

        await context.bot.send_message(w["user_id"],"✅ Đã duyệt rút tiền.")
        log(query.from_user.id,f"Duyệt {wid}")

    else:
        cursor.execute("UPDATE withdraws SET status='rejected' WHERE id=?",(wid,))
        conn.commit()

        await context.bot.send_message(w["user_id"],"❌ Rút tiền bị từ chối.")
        log(query.from_user.id,f"Từ chối {wid}")

    await query.edit_message_text("Đã xử lý.")

# ================= EXPORT =================
async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id):
        return

    wb = Workbook()
    ws = wb.active
    ws.append(["User ID","Balance","VIP"])

    cursor.execute("SELECT * FROM users")
    for u in cursor.fetchall():
        ws.append([u["id"],u["balance"],u["vip"]])

    wb.save("users.xlsx")
    await update.message.reply_document(open("users.xlsx","rb"))
# ================= CỘNG TIỀN ADMIN =================
async def addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Kiểm tra quyền admin
    if not is_admin(uid):
        await update.message.reply_text("❌ Bạn không có quyền.")
        return

    # Kiểm tra cú pháp
    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /addmoney user_id amount")
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except:
        await update.message.reply_text("Sai định dạng số.")
        return

    # Kiểm tra user tồn tại
    cursor.execute("SELECT * FROM users WHERE id=?", (target_id,))
    target = cursor.fetchone()

    if not target:
        await update.message.reply_text("User không tồn tại.")
        return

    # Cộng tiền
    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE id=?",
        (amount, target_id)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Đã cộng {amount} VND cho {target_id}")
    await context.bot.send_message(target_id, f"🎉 Bạn được cộng {amount} VND")

    log(uid, f"Admin cộng {amount} cho {target_id}")


# ================= MAIN =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rutbank", rutbank))
    app.add_handler(CommandHandler("export", export_excel))
    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^(approve_|reject_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

    print("BOT PRO+ ĐANG CHẠY")
    app.run_polling()

if __name__ == "__main__":
    main()
