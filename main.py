#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🛠 TECH TASK - Telegram bot (для Python 3.13 и python-telegram-bot >= 21)
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- Конфиг -----------------
BOT_TOKEN = "8265362344:AAHib1QEWKBzTIjt_9b_lC7W3p-BHs3fvyQ"  # муляж токена
TECH_CHAT_ID = -4844266445  # ID чата техников
DB_PATH = "tasks.db"

# ----------------- Логирование -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ----------------- Работа с БД -----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manager_id INTEGER,
        manager_username TEXT,
        content TEXT,
        status TEXT,
        tech_id INTEGER,
        tech_username TEXT,
        tech_chat_message_id INTEGER,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def create_task(manager_id, manager_username, content):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tasks (manager_id, manager_username, content, status, created_at, updated_at)
        VALUES (?, ?, ?, 'new', ?, ?)
    """, (manager_id, manager_username, content, now, now))
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def set_tech_message_id(task_id, msg_id):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET tech_chat_message_id = ?, updated_at = ? WHERE id = ?", (msg_id, now, task_id))
    conn.commit()
    conn.close()


def get_task(task_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    keys = ["id","manager_id","manager_username","content","status","tech_id","tech_username","tech_chat_message_id","created_at","updated_at"]
    return dict(zip(keys, row))


def take_task_db(task_id, tech_id, tech_username):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE tasks
        SET tech_id = ?, tech_username = ?, status = 'in_progress', updated_at = ?
        WHERE id = ?
    """, (tech_id, tech_username, now, task_id))
    conn.commit()
    conn.close()


def update_status_db(task_id, status, tech_id=None, tech_username=None):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE tasks
        SET status = ?, tech_id = COALESCE(?, tech_id), tech_username = COALESCE(?, tech_username), updated_at = ?
        WHERE id = ?
    """, (status, tech_id, tech_username, now, task_id))
    conn.commit()
    conn.close()


def list_manager_tasks(manager_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, content, status, tech_username, created_at FROM tasks WHERE manager_id = ? ORDER BY id DESC", (manager_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ----------------- Клавиатуры -----------------
def kb_take(task_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔏 Беру таску", callback_data=f"take:{task_id}")]])


def kb_after_take(task_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Done", callback_data=f"done:{task_id}"),
        InlineKeyboardButton("🟡 On Hold", callback_data=f"hold:{task_id}"),
        InlineKeyboardButton("🔴 Cancel Task", callback_data=f"cancel:{task_id}")
    ]])


# ----------------- Форматирование -----------------
def format_task_message(task_id, manager_username, content, status_line=None):
    lines = [
        f"🛠 Новая таска от @{manager_username if manager_username else 'менеджера'}",
        f"# {task_id}",
        content
    ]
    if status_line:
        lines.append("")
        lines.append(status_line)
    return "\n".join(lines)


# ----------------- Хэндлеры -----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я — 🛠 TECH TASK бот.\n"
        "Менеджеры: /connect <текст задачи>\n"
        "Команды: /mytasks — список ваших задач"
    )


async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text or ""
    parts = raw.split(" ", 1)
    content = parts[1].strip() if len(parts) > 1 else ""
    if not content:
        await update.message.reply_text("Пожалуйста, укажите текст таски после /connect.")
        return

    manager = update.effective_user
    manager_id = manager.id
    manager_username = manager.username or manager.full_name or "manager"

    task_id = create_task(manager_id, manager_username, content)
    text = format_task_message(task_id, manager_username, content)

    sent = await context.bot.send_message(chat_id=TECH_CHAT_ID, text=text, reply_markup=kb_take(task_id))
    set_tech_message_id(task_id, sent.message_id)

    await update.message.reply_text(f"✅ Таска #{task_id} отправлена в тех-чат.")


async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    manager = update.effective_user
    rows = list_manager_tasks(manager.id)
    if not rows:
        await update.message.reply_text("У вас пока нет задач.")
        return
    text_lines = []
    for r in rows:
        tid, content, status, tech_username, created_at = r
        status_readable = {
            "new": "🟦 Новый",
            "in_progress": "🟧 В работе",
            "done": "🟢 Выполнено",
            "on_hold": "🟡 On Hold",
            "cancelled": "🔴 Отменено"
        }.get(status, status)
        tech_part = f" — @{tech_username}" if tech_username else ""
        text_lines.append(f"#{tid} {status_readable}{tech_part}\n{content}")
    await update.message.reply_text("\n\n".join(text_lines))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user = query.from_user
    username = user.username or user.full_name or "tech"

    if data.startswith("take:"):
        task_id = int(data.split(":")[1])
        task = get_task(task_id)
        if not task or task["status"] != "new":
            await query.answer("Эту таску уже взяли или она закрыта.", show_alert=True)
            return

        take_task_db(task_id, user.id, username)
        status_line = f"👤 Взято в работу @{username}"
        new_text = format_task_message(task_id, task["manager_username"], task["content"], status_line)
        await query.edit_message_text(text=new_text, reply_markup=kb_after_take(task_id))
        return

    if any(data.startswith(pref) for pref in ("done:", "hold:", "cancel:")):
        action, raw = data.split(":")
        task_id = int(raw)
        task = get_task(task_id)
        if not task:
            await query.answer("Таска не найдена.", show_alert=True)
            return

        if action == "done":
            status_text = f"🟢 Done by @{username}"
            db_status = "done"
        elif action == "hold":
            status_text = f"🟡 On Hold by @{username}"
            db_status = "on_hold"
        else:
            status_text = f"🔴 Cancelled by @{username}"
            db_status = "cancelled"

        update_status_db(task_id, db_status, user.id, username)
        new_text = format_task_message(task_id, task["manager_username"], task["content"], status_text)
        await query.edit_message_text(text=new_text)

        try:
            await context.bot.send_message(chat_id=task["manager_id"], text=f"🔔 Таска #{task_id} обновлена: {status_text}")
        except Exception:
            pass


# ----------------- Запуск -----------------
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("connect", cmd_connect))
    app.add_handler(CommandHandler("mytasks", cmd_mytasks))
    app.add_handler(CallbackQueryHandler(callback_handler))
    logger.info("✅ Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
