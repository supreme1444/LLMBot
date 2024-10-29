from sqlalchemy import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_openai import ChatOpenAI

from app.appi import message_handler

# Инициализация клиента OpenAI с заданным API ключом и URL
client = ChatOpenAI(
    api_key="sk-KMHrRUpHbijEdt5ViGuRWt4uVQMUHFVy",
    base_url="https://api.proxyapi.ru/openai/v1",
)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет. Чем могу помочь?")
# Основная функция для запуска бота
def main():
    application = ApplicationBuilder().token("8050637207:AAHkgXzJ4hB9zH9w6Otr-wiu-EQjPczmyK8").build()
    application.add_handler(CommandHandler("start", start))  # Обработчик команды /start
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))  # Обработчик текстовых сообщений
    application.run_polling()  # Запуск бота

# Проверка, запускается ли скрипт напрямую
if __name__ == '__main__':
    main()
