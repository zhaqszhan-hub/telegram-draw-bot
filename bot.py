import os
import random
import sqlite3
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

# --- База данных ---
conn = sqlite3.connect("draws.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    admin_id INTEGER,
    max_participants INTEGER,
    started INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_id INTEGER,
    user_id INTEGER,
    username TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_id INTEGER,
    giver_id INTEGER,
    receiver_id INTEGER
)
""")

conn.commit()


# --- Команды ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет 👋\n\n"
        "Команды:\n"
        "/create Название Количество - создать жеребьевку\n"
        "/join ID - вступить\n"
        "/start_draw ID - провести жеребьевку\n"
        "/pairs ID - показать пары (только админ)"
    )


async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /create Название Количество")
        return

    name = context.args[0]
    max_participants = int(context.args[1])
    admin_id = update.effective_user.id

    cursor.execute(
        "INSERT INTO draws (name, admin_id, max_participants) VALUES (?, ?, ?)",
        (name, admin_id, max_participants)
    )
    conn.commit()

    draw_id = cursor.lastrowid

    await update.message.reply_text(
        f"Жеребьевка создана ✅\n"
        f"ID: {draw_id}\n"
        f"Название: {name}\n"
        f"Участников: {max_participants}\n\n"
        f"Отправь участникам команду:\n"
        f"/join {draw_id}"
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /join ID")
        return

    draw_id = int(context.args[0])
    user = update.effective_user

    cursor.execute("SELECT * FROM draws WHERE id = ?", (draw_id,))
    draw = cursor.fetchone()

    if not draw:
        await update.message.reply_text("Жеребьевка не найдена.")
        return

    cursor.execute(
        "SELECT * FROM participants WHERE draw_id = ? AND user_id = ?",
        (draw_id, user.id)
    )
    if cursor.fetchone():
        await update.message.reply_text("Ты уже зарегистрирован.")
        return

    cursor.execute(
        "INSERT INTO participants (draw_id, user_id, username) VALUES (?, ?, ?)",
        (draw_id, user.id, user.username or user.first_name)
    )
    conn.commit()

    await update.message.reply_text("Ты успешно зарегистрирован ✅")

    # уведомление админа
    admin_id = draw[2]
    await context.bot.send_message(
        chat_id=admin_id,
        text=f"Новый участник в жеребьевке {draw_id}: {user.username or user.first_name}"
    )


async def start_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /start_draw ID")
        return

    draw_id = int(context.args[0])
    user_id = update.effective_user.id

    cursor.execute("SELECT * FROM draws WHERE id = ?", (draw_id,))
    draw = cursor.fetchone()

    if not draw:
        await update.message.reply_text("Жеребьевка не найдена.")
        return

    if draw[2] != user_id:
        await update.message.reply_text("Только админ может запустить жеребьевку.")
        return

    cursor.execute("SELECT user_id FROM participants WHERE draw_id = ?", (draw_id,))
    participants = [row[0] for row in cursor.fetchall()]

    if len(participants) < draw[3]:
        await update.message.reply_text("Зарегистрировались не все участники.")
        return

    receivers = participants.copy()
    valid = False

    while not valid:
        random.shuffle(receivers)
        valid = all(p != r for p, r in zip(participants, receivers))
        # исключаем взаимные пары
        for p, r in zip(participants, receivers):
            if participants.index(r) == receivers.index(p):
                valid = False
                break

    for giver, receiver in zip(participants, receivers):
        cursor.execute(
            "INSERT INTO pairs (draw_id, giver_id, receiver_id) VALUES (?, ?, ?)",
            (draw_id, giver, receiver)
        )
        await context.bot.send_message(
            chat_id=giver,
            text=f"Тебе выпал участник с ID: {receiver}"
        )

    conn.commit()

    cursor.execute("UPDATE draws SET started = 1 WHERE id = ?", (draw_id,))
    conn.commit()

    await update.message.reply_text("Жеребьевка проведена 🎉")


async def pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /pairs ID")
        return

    draw_id = int(context.args[0])
    user_id = update.effective_user.id

    cursor.execute("SELECT * FROM draws WHERE id = ?", (draw_id,))
    draw = cursor.fetchone()

    if not draw or draw[2] != user_id:
        await update.message.reply_text("Только админ может смотреть пары.")
        return

    cursor.execute(
        "SELECT giver_id, receiver_id FROM pairs WHERE draw_id = ?",
        (draw_id,)
    )
    pairs_list = cursor.fetchall()

    if not pairs_list:
        await update.message.reply_text("Пары еще не сформированы.")
        return

    text = "Пары:\n\n"
    for giver, receiver in pairs_list:
        text += f"{giver} ➝ {receiver}\n"

    await update.message.reply_text(text)


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("start_draw", start_draw))
    app.add_handler(CommandHandler("pairs", pairs))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
