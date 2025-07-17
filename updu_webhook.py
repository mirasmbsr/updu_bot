import os
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

TOKEN = os.getenv("BOT_TOKEN") or "8166321371:AAG56x3nbgv3KwyejtJqdWmORxp84p8av0Y"

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# ======= Твои хендлеры команд =========

def start(update, context):
    update.message.reply_text('Бот работает на вебхуках!')

def habit(update, context):
    update.message.reply_text('Твоя привычка успешно добавлена!')

def proof(update, context):
    update.message.reply_text('Здесь будет обработка доказательств!')

def echo(update, context):
    update.message.reply_text(f'Ты прислал: {update.message.text}')

# Пример хендлера для фото (например, для proof)
def receive_proof(update, context):
    if not update.message or not update.message.from_user:
        return
    user = update.message.from_user.first_name
    update.message.reply_text(f"{user} отправил доказательство!")

# ======= Регистрируем хендлеры =========

dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('habit', habit))
dispatcher.add_handler(CommandHandler('proof', proof))
dispatcher.add_handler(MessageHandler(Filters.photo, receive_proof))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# ======= Webhook endpoint для Telegram ========

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return 'Updu бот на вебхуках!'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)