import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext

# Простая in-memory база (замени на SQLite для продакшена)
users = {}         # user_id -> {'habit': str, 'streak': int}
waiting_proof = {} # user_id -> True/False
pending_reports = {} # report_id -> dict

REPORT_ID = 1

# ===== НАСТРОЙКИ =====
GROUP_ID = -4828175895 # твой group id (замени на свой)
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Привет! Я Updu-бот. Введи /habit <текст привычки>, чтобы начать."
    )

def habit(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    habit_text = ' '.join(context.args)
    if not habit_text:
        update.message.reply_text("Пример: /habit читать 10 страниц")
        return
    users[user_id] = {'habit': habit_text, 'streak': 0, 'username': username}
    update.message.reply_text(f"Привычка сохранена: {habit_text}")

def done(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in users:
        update.message.reply_text("Сначала задай привычку через /habit ...")
        return
    waiting_proof[user_id] = True
    update.message.reply_text("Пришли доказательство: фото, видео или текст!")

def receive_proof(update: Update, context: CallbackContext):
    if not update.message or not update.message.from_user:
        return
    user_id = update.message.from_user.id
    # ... остальной код

    if not waiting_proof.get(user_id):
        return
    username = users[user_id]['username']
    habit_text = users[user_id]['habit']
    global REPORT_ID
    report_id = REPORT_ID
    REPORT_ID += 1

    # Определяем тип доказательства
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

    # Сохраняем отчёт и сбрасываем ожидание
    waiting_proof[user_id] = False
    pending_reports[report_id] = {
        'user_id': user_id,
        'habit': habit_text,
        'username': username,
        'proof': proof,
        'media_type': media_type,
        'approvers': set(),
        'deniers': set()
    }

    # Формируем сообщение в группу с кнопками
    proof_text = f"@{username} говорит, что выполнил привычку:\n*{habit_text}*\n\nВот его доказательство:"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{report_id}")],
        [InlineKeyboardButton("❌ Опровергнуть", callback_data=f"deny_{report_id}")]
    ])

    if media_type == 'photo':
        context.bot.send_photo(chat_id=GROUP_ID, photo=proof, caption=proof_text, reply_markup=kb, parse_mode='Markdown')
    elif media_type == 'video':
        context.bot.send_video(chat_id=GROUP_ID, video=proof, caption=proof_text, reply_markup=kb, parse_mode='Markdown')
    elif media_type == 'text':
        context.bot.send_message(chat_id=GROUP_ID, text=f"{proof_text}\n\n{proof}", reply_markup=kb, parse_mode='Markdown')

    update.message.reply_text("Доказательство отправлено в группу на подтверждение!")

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    action, report_id = data.split('_')
    report_id = int(report_id)
    report = pending_reports.get(report_id)
    if not report:
        query.answer("Этот отчёт уже закрыт!")
        return
    if user_id == report['user_id']:
        query.answer("Ты не можешь голосовать за себя!")
        return

    if action == 'approve':
        if user_id in report['approvers']:
            query.answer("Ты уже голосовал 'Подтвердить'")
            return
        report['approvers'].add(user_id)
        report['deniers'].discard(user_id)
        query.answer("Ты подтвердил выполнение")
    elif action == 'deny':
        if user_id in report['deniers']:
            query.answer("Ты уже голосовал 'Опровергнуть'")
            return
        report['deniers'].add(user_id)
        report['approvers'].discard(user_id)
        query.answer("Ты опроверг выполнение")

    # Подсчёт голосов (50%+ подтверждений)
    group_members = 5  # Временно! Замени на реальное число участников группы
    votes = len(report['approvers']) + len(report['deniers'])
    needed = group_members // 2 + 1
    if len(report['approvers']) >= needed:
        users[report['user_id']]['streak'] += 1
        context.bot.send_message(chat_id=GROUP_ID, text=f"✅ @{report['username']}, твоя привычка подтверждена! Стрик: {users[report['user_id']]['streak']} дней")
        pending_reports.pop(report_id)
    elif len(report['deniers']) >= needed:
        users[report['user_id']]['streak'] = 0
        context.bot.send_message(chat_id=GROUP_ID, text=f"❌ @{report['username']}, выполнение отклонено! Стрик сброшен.")
        pending_reports.pop(report_id)

def streak(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    streak = users.get(user_id, {}).get('streak', 0)
    update.message.reply_text(f"Твой стрик: {streak} дней подряд.")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("habit", habit))
    dp.add_handler(CommandHandler("done", done))
    dp.add_handler(CommandHandler("streak", streak))
    dp.add_handler(CallbackQueryHandler(button))
    # Хэндлер для текста, фото, видео — только если ждём доказательство
    dp.add_handler(MessageHandler(
        Filters.chat(GROUP_ID) & (Filters.text | Filters.photo | Filters.video),
        receive_proof
    ))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
