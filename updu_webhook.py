import os
import json
import logging
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler




def save_users():
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f)

def load_users():
    global users
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}





# Простая in-memory база (замени на SQLite для продакшена)
users = {}            # group_id -> {user_id: {...}}
waiting_proof = {}    # group_id -> {user_id: True/False}
pending_reports = {}  # group_id -> {report_id: {...}}
REPORT_ID = {}        # group_id -> int


GROUP_ID = -4828175895  # твой group id (замени на свой)
TOKEN = os.getenv("BOT_TOKEN") or "ТВОЙ_ТОКЕН_СЮДА"

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)
BOT_ID = None
pending_habit = {}  # user_id -> habit_text

def start(update, context):
    update.message.reply_text("Привет! Я Updu-бот. Введи /habit <текст привычки>, чтобы начать.")

def habit(update, context):
    group_id = update.effective_chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    habit_text = ' '.join(context.args)
    if not habit_text:
        update.message.reply_text("Пример: /habit читать 10 страниц")
        return

    # Сохраняем в ожидание подтверждения
    pending_habit[user_id] = (group_id, habit_text)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data="habit_confirm"),
            InlineKeyboardButton("❌ Нет", callback_data="habit_cancel")
        ]
    ])
    update.message.reply_text(
        f"Вы уверены, что хотите изменить привычку на:\n*{habit_text}*?",
        reply_markup=kb,
        parse_mode="Markdown"
    )


def done(update, context):
    group_id = update.effective_chat.id
    user_id = update.message.from_user.id
    if group_id not in users or user_id not in users[group_id]:
        update.message.reply_text("Сначала задай привычку через /habit ...")
        return
    if group_id not in waiting_proof:
        waiting_proof[group_id] = {}
    waiting_proof[group_id][user_id] = True
    update.message.reply_text("Пришли доказательство: фото, видео или текст!")


def receive_proof(update, context):
    if not update.message or not update.message.from_user:
        return
    group_id = update.effective_chat.id
    user_id = update.message.from_user.id

    if group_id not in waiting_proof or not waiting_proof[group_id].get(user_id):
        return
    if group_id not in users or user_id not in users[group_id]:
        return

    if group_id not in REPORT_ID:
        REPORT_ID[group_id] = 1
    report_id = REPORT_ID[group_id]
    REPORT_ID[group_id] += 1

    if group_id not in pending_reports:
        pending_reports[group_id] = {}

    username = users[group_id][user_id]['username']
    habit_text = users[group_id][user_id]['habit']

    proof = None
    if update.message.photo:
        proof = update.message.photo[-1].file_id
        media_type = 'photo'
    elif update.message.video:
        proof = update.message.video.file_id
        media_type = 'video'
    elif update.message.text:
        proof = update.message.text
        media_type = 'text'
    else:
        update.message.reply_text("Пришли фото, видео или текст!")
        return

    waiting_proof[group_id][user_id] = False
    pending_reports[group_id][report_id] = {
        'user_id': user_id,
        'habit': habit_text,
        'username': username,
        'proof': proof,
        'media_type': media_type,
        'approvers': [],
        'deniers': []
    }

    proof_text = (
        f"@{username} говорит, что выполнил привычку:\n*{habit_text}*\n\nВот его доказательство:\n"
        f"\n✅ 0 подтверждений"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить (0)", callback_data=f"approve_{report_id}")],
        [InlineKeyboardButton("❌ Опровергнуть (0)", callback_data=f"deny_{report_id}")]
    ])

    if media_type == 'photo':
        context.bot.send_photo(chat_id=group_id, photo=proof, caption=proof_text, reply_markup=kb, parse_mode='Markdown')
    elif media_type == 'video':
        context.bot.send_video(chat_id=group_id, video=proof, caption=proof_text, reply_markup=kb, parse_mode='Markdown')
    elif media_type == 'text':
        context.bot.send_message(chat_id=group_id, text=f"{proof_text}\n\n{proof}", reply_markup=kb, parse_mode='Markdown')

    update.message.reply_text("Доказательство отправлено в группу на подтверждение!")

def button(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # --- Обработка подтверждения смены привычки ---
    if data == "habit_confirm":
        if user_id in pending_habit:
            group_id, habit_text = pending_habit.pop(user_id)
            username = query.from_user.username
            if group_id not in users:
                users[group_id] = {}
            users[group_id][user_id] = {'habit': habit_text, 'streak': 0, 'username': username}
            query.edit_message_text(f"Привычка изменена на: *{habit_text}*", parse_mode="Markdown")
        else:
            query.answer("Нет привычки для подтверждения.")
        return

    if data == "habit_cancel":
        if user_id in pending_habit:
            pending_habit.pop(user_id)
            query.edit_message_text("Изменение привычки отменено.")
        else:
            query.answer("Нет привычки для отмены.")
        return

    # --- ДАЛЬШЕ обычный обработчик кнопок ---
    group_id = query.message.chat.id

    # data должен быть вида approve_123 или deny_123
    if '_' not in data:
        query.answer("Неверный формат кнопки.")
        return

    action, report_id = data.split('_')
    report_id = int(report_id)
    report = pending_reports.get(group_id, {}).get(report_id)
    if not report:
        query.answer("Этот отчёт уже закрыт!")
        return
    if user_id == report['user_id'] or user_id == BOT_ID:
        query.answer("Ты не можешь голосовать за себя или за бота!")
        return

    changed = False
    if action == 'approve':
        if user_id in report['approvers']:
            query.answer("Ты уже голосовал 'Подтвердить'")
            return
        report['approvers'].append(user_id)
        if user_id in report['deniers']:
            report['deniers'].remove(user_id)
        changed = True
        query.answer("Ты подтвердил выполнение")
    elif action == 'deny':
        if user_id in report['deniers']:
            query.answer("Ты уже голосовал 'Опровергнуть'")
            return
        report['deniers'].append(user_id)
        if user_id in report['approvers']:
            report['approvers'].remove(user_id)
        changed = True
        query.answer("Ты опроверг выполнение")

    group_members = len(users.get(group_id, {}))
    if BOT_ID and BOT_ID in users.get(group_id, {}):
        group_members -= 1
    needed = group_members // 2 + 1 if group_members > 1 else 1

    approve_count = len(report['approvers'])
    deny_count = len(report['deniers'])

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Подтвердить ({approve_count})", callback_data=f"approve_{report_id}")],
        [InlineKeyboardButton(f"❌ Опровергнуть ({deny_count})", callback_data=f"deny_{report_id}")]
    ])
    try:
        query.edit_message_reply_markup(reply_markup=kb)
    except Exception:
        pass

    if approve_count >= needed:
        users[group_id][report['user_id']]['streak'] += 1
        context.bot.send_message(
            chat_id=group_id,
            text=(f"✅ @{report['username']}, твоя привычка подтверждена!\n"
                  f"Стрик: {users[group_id][report['user_id']]['streak']} дней подряд! 🎉")
        )
        pending_reports[group_id].pop(report_id)
    elif deny_count >= needed:
        users[group_id][report['user_id']]['streak'] = 0
        context.bot.send_message(
            chat_id=group_id,
            text=f"❌ @{report['username']}, выполнение отклонено! Стрик сброшен."
        )
        pending_reports[group_id].pop(report_id)


def streak(update, context):
    group_id = update.effective_chat.id
    user_id = update.message.from_user.id
    streak = users.get(group_id, {}).get(user_id, {}).get('streak', 0)
    update.message.reply_text(f"Твой стрик: {streak} дней подряд.")


# === Регистрация хендлеров ===
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("habit", habit))
dispatcher.add_handler(CommandHandler("done", done))
dispatcher.add_handler(CommandHandler("streak", streak))
dispatcher.add_handler(CallbackQueryHandler(button))
dispatcher.add_handler(MessageHandler(Filters.photo | Filters.video | Filters.text, receive_proof))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'

@app.route('/')
def index():
    
    return 'Updu бот на вебхуках!'

def main():
    global BOT_ID
    BOT_ID = bot.get_me().id
    load_users()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()


