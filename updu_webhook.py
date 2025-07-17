import os
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

TOKEN = os.getenv("BOT_TOKEN") or "8166321371:AAG56x3nbgv3KwyejtJqdWmORxp84p8av0Y"

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# ======= твои хендлеры =========
def start(update, context):
    update.message.reply_text('Бот работает на вебхуках!')

def echo(update, context):
    update.message.reply_text(f'Ты прислал: {update.message.text}')

dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
# ================================

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return 'Updu бот на вебхуках!'

if __name__ == '__main__':
    # Render слушает только этот порт!
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
