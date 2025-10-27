#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🛠 TECH TASK - Telegram bot
Совместим с python-telegram-bot==20.8

Перед деплоем рекомендуется:
- хранить токен в переменных окружения (BOT_TOKEN)
- TECH_CHAT_ID тоже в env, но по умолчанию установлен муляж
"""

import os
import logging
import sqlite3
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- Конфиг (берём из env, если есть) -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8265362344:AAHib1QEWKBzTIjt_9b_lC7W3p-BHs3fvyQ")  # муляж по умолчанию
try:
    TECH_CHAT_ID = int(os.getenv("TECH_CHAT_ID", "-4844266445"))
except Exception:
    TECH_CHAT_ID = -4844266445
DB_PATH = os.getenv("DB_PATH", "tasks.db")

# ----------------- Логирование -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ----------------- Работа с БД -----------------
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
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
    """
    )
    conn.commit()
    conn.close()


def create_task(manager_id: int, manager_username: str, content: str) -> int:
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tasks (manager_id, manager_username, content, status, created_at, updated_at)
        VALUES (?, ?, ?, 'new', ?, ?)
    """,
        (manager_id, manager_username, content, now, now),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def set_tech_message_id(task_id: int, msg_id: int) -> None:
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET tech_chat_message_id = ?, updated_at = ? WHERE id = ?",
        (msg_id, now, task_id),
    )
    conn.commit()
    conn.close()


def get_task(task_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, manager_id, manager_username, content, status, tech_id, tech_username, tech_chat_message_id, created_at, updated_at
        FROM tasks WHERE id = ?
    """,
        (task_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    keys = [
        "id",
        "manager_id",
        "manager_username",
        "content",
        "status",
        "tech_id",
        "tech_username",
        "tech_chat_message_id",
        "created_at",
        "updated_at",
    ]
    return dict(zip(keys, row))


def take_task_db(task_id: int, tech_id: int, tech_username: str) -> None:
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tasks
        SET tech_id = ?, tech_username = ?, status = 'in_progress', updated_at = ?
        WHERE id = ?
    """,
        (tech_id, tech_username, now, task_id),
    )
    conn.commit()
    conn.close()


def update_status_db(task_id: int, status: str, tech_id: Optional[int] = None, tech_username: Optional[str] = None) -> None:
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if tech_id is not None or tech_username is not None:
        cur.execute(
            """
            UPDATE tasks
            SET status = ?, tech_id = COALESCE(?, tech_id), tech_username = COALESCE(?, tech_username), updated_at = ?
            WHERE id = ?
        """,
            (status, tech_id, tech_username, now, task_id),
        )
    else:
        cur.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now, task_id))
    conn.commit()
    conn.close()


def list_manager_tasks(manager_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, content, status, tech_username, created_at FROM tasks WHERE manager_id = ? ORDER BY id DESC", (manager_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ----------------- Клавиатуры / форматирование -----------------
def kb_take(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔏 Беру таску", callback_data=f"take:{task_id}")]])


def kb_after_take(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🟢 Done", callback_data=f"done:{task_id}"),
                InlineKeyboardButton("🟡 On Hold", callback_data=f"hold:{task_id}"),
                InlineKeyboardButton("🔴 Cancel Task", callback_data=f"cancel:{task_id}"),
            ]
        ]
    )


def format_task_message(task_id: int, manager_username: str, content: str, status_line: Optional[str] = None) -> str:
    lines = []
    lines.append("🛠 Новая таска от " + (f"@{manager_username}" if manager_username else "менеджера"))
    lines.append(f"# {task_id}")
    lines.append(content)
    if status_line:
        lines.append("")  # blank line
        lines.append(status_line)
    return "\n".join(lines)


# ----------------- Хэндлеры -----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я — 🛠 TECH TASK бот.\n"
        "Менеджеры: /connect <текст задачи>\n"
        "Команды для менеджеров: /mytasks — список ваших задач"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/connect <текст> — создать таску\n"
        "/mytasks — посмотреть свои таски\n"
        "/start — приветствие\n"
        "/help — помощь"
    )


async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text or ""
    parts = raw.split(" ", 1)
    if len(parts) > 1 and parts[1].strip():
        content = parts[1].strip()
    else:
        rest = raw.split("\n", 1)
        content = rest[1].strip() if len(rest) > 1 else ""

    if not content:
        await update.message.reply_text("Пожалуйста, укажите текст таски после /connect.")
        return

    manager = update.effective_user
    manager_id = manager.id
    manager_username = manager.username or manager.full_name or "manager"

    # создаём таску
    task_id = create_task(manager_id, manager_username, content)
    logger.info(f"Создана таска #{task_id} от @{manager_username}")

    # отправляем в тех-чат
    text = format_task_message(task_id, manager_username, content)
    try:
        sent = await context.bot.send_message(chat_id=TECH_CHAT_ID, text=text, reply_markup=kb_take(task_id))
    except Exception as e:
        logger.exception("Failed to send to tech chat")
        await update.message.reply_text("Ошибка: не удалось отправить таску в тех-чат. Проверьте что бот добавлен в чат и имеет права.")
        return

    # сохраняем message_id
    set_tech_message_id(task_id, sent.message_id)

    # подтверждение менеджеру
    await update.message.reply_text(f"✅ Таска #{task_id} отправлена в технический отдел.")


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
            "cancelled": "🔴 Отменено",
        }.get(status, status)
        tech_part = f" — @{tech_username}" if tech_username else ""
        text_lines.append(f"#{tid} {status_readable}{tech_part}\n{content}")
    await update.message.reply_text("\n\n".join(text_lines))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    user = query.from_user
    username = user.username or user.full_name or "tech"

    # TAKE
    if data.startswith("take:"):
        try:
            task_id = int(data.split(":", 1)[1])
        except Exception:
            await query.answer("Неверный ID.")
            return

        task = get_task(task_id)
        if not task:
            await query.answer("Таска не найдена.", show_alert=True)
            return

        if task["status"] != "new":
            await query.answer("Эту таску уже взяли или она закрыта.", show_alert=True)
            return

        # апдейт бд
        take_task_db(task_id, user.id, username)

        # редактируем сообщение в тех-чате
        status_line = f"👤 Взято в работу @{username}"
        new_text = format_task_message(task_id, task["manager_username"], task["content"], status_line=status_line)
        try:
            # пытаемся редактировать по сохранённому message_id в чате техников
            await context.bot.edit_message_text(chat_id=TECH_CHAT_ID, message_id=task["tech_chat_message_id"], text=new_text, reply_markup=kb_after_take(task_id))
        except Exception:
            # fallback: редактируем само сообщение, откуда пришёл callback
            try:
                await query.edit_message_text(text=new_text, reply_markup=kb_after_take(task_id))
            except Exception:
                logger.exception("Failed to edit message on take")
        await query.answer("Таску взяли в работу ✅")
        return

    # DONE / HOLD / CANCEL
    if any(data.startswith(pref) for pref in ("done:", "hold:", "cancel:")):
        try:
            action, raw = data.split(":", 1)
            task_id = int(raw)
        except Exception:
            await query.answer("Неверные данные.")
            return

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
            status_text = f"🔴 Cancel Task by @{username}"
            db_status = "cancelled"

        # обновляем бд
        update_status_db(task_id, db_status, tech_id=user.id, tech_username=username)

        # редактируем сообщение в тех-чате — убираем кнопки, добавляем статус
        new_text = format_task_message(task_id, task["manager_username"], task["content"], status_line=status_text)
        try:
            await context.bot.edit_message_text(chat_id=TECH_CHAT_ID, message_id=task["tech_chat_message_id"], text=new_text)
        except Exception:
            try:
                await query.edit_message_text(text=new_text)
            except Exception:
                logger.exception("Failed to edit message on final status")

        # уведомляем менеджера
        try:
            if task["manager_id"]:
                await context.bot.send_message(chat_id=task["manager_id"], text=f"🔔 Таска #{task_id} обновлена: {status_text}")
        except Exception:
            logger.exception("Failed to notify manager")

        await query.answer("Статус обновлён.")
        return

    # default
    await query.answer("Неизвестное действие.", show_alert=True)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте /help.")


# ----------------- Запуск -----------------
def main() -> None:
    init_db()
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Set environment variable BOT_TOKEN or hardcode it (not recommended).")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("connect", cmd_connect))  # менеджеры создают таски этой командой
    app.add_handler(CommandHandler("mytasks", cmd_mytasks))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info("Бот запущен и готов принимать задачи.")
    app.run_polling()


if __name__ == "__main__":
    main()
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

    
