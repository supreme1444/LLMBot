
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
import numpy as np
from sklearn.cluster import KMeans
import spacy
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# Загрузка модели для обработки естественного языка
nlp = spacy.load("ru_core_news_sm")

# Инициализация OpenAI клиента
client = ChatOpenAI(
    api_key="sk-KMHrRUpHbijEdt5ViGuRWt4uVQMUHFVy",
    base_url="https://api.proxyapi.ru/openai/v1",
)

# Подключение к базе данных SQLite
conn = sqlite3.connect("al.db")
cursor = conn.cursor()

# Создание таблиц, если они не существуют
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT
)''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()
history = []
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет. Чем могу помочь?")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    message = update.message.text

    # Сохранение пользователя в базе данных
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)
    ''', (user_id, username))
    conn.commit()

    # Сохранение сообщения в базе данных
    cursor.execute('''
    INSERT INTO messages (user_id, message) VALUES (?, ?)
    ''', (user_id, message))
    conn.commit()

    # Обработка сообщения
    intent = handle_message_enter(message)
    if intent is not None:
        response = process_intent(intent, user_id)
        await update.message.reply_text(response)
    else:
        # Создание шаблона подсказки
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Вы — высококлассный технический писатель."),
            ("user", "{input}")
        ])
        # Создание цепочки
        chain = prompt | client | StrOutputParser()
        # Хранение истории сообщений
        history.append({"role": "user", "content": message})
        context_input = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        response = chain.invoke({"input": context_input})
        # Добавление ответа бота в историю
        history.append({"role": "bot", "content": response})

        response
        await update.message.reply_text(response)


def handle_message_enter(message):
    intents = {
        "last_conversation": ["последний разговор", "предыдущее сообщения", "общение", " все диалоги"],
        "user_list": ["список пользователей", "ник", "кто", "со мной", "общались с тобой", "юзер, ", "все кто"],
        "frequent_questions": ["часто", "задаваемые", "частые вопросы", "часто спрашивают", "что чаще", "что чаще спрашивают",
                               "что задают", "самый частый", ],
        "censorship": ["censorship_bot"],
        "rat_bot": ["другие","другие пользователи","запросы других","других юзеров","вопросы других","о чем","диалоги других"]
    }

    doc = nlp(message.lower())

    for intent, keywords in intents.items():
        if any(keyword in doc.text for keyword in keywords):
            return intent
    return None


def process_intent(intent, user_id):
    if intent == "last_conversation":
        cursor.execute('''
            SELECT message FROM messages WHERE user_id = ? ORDER BY id DESC
        ''', (user_id,))
        messages = cursor.fetchall()
        if messages:
            conversation = "\n".join([msg[0] for msg in messages if msg[0] is not None])
            return f"Ваши последние сообщения:\n{conversation}"
        else:
            return "У вас нет сообщений."
    elif intent == "user_list":
        cursor.execute('SELECT username FROM users')
        users = cursor.fetchall()
        user_list = ", ".join([user[0] for user in users if user[0] is not None])
        if user_list:
            return f"Список пользователей: {user_list}"
        else:
            return "Пользователей нет."

    elif intent == "frequent_questions":
        cursor.execute('''
            SELECT message FROM messages ORDER BY id DESC
        ''')
        messages_avr = cursor.fetchall()
        vectors = np.array([nlp(message[0]).vector for message in messages_avr])
        kmeans = KMeans(n_clusters=10)
        kmeans.fit(vectors)
        labels, counts = np.unique(kmeans.labels_, return_counts=True)
        popular_cluster_index = labels[np.argmax(counts)]
        cluster_questions = [messages_avr[i][0] for i in range(len(messages_avr)) if
                             kmeans.labels_[i] == popular_cluster_index]
        return f"Самый популярный вопрос: {cluster_questions[0]}"
    elif intent == "censorship":
        cursor.execute('SELECT id, user_id, message FROM messages ORDER BY id DESC')
        messages = cursor.fetchall()
        with open("censorship.txt", 'r', encoding="utf-8") as file:
            censorship_words = file.read().splitlines()
            matching_user_ids = set()
            for message in messages:
                message_id, user_id, message_text = message
                message_text_lower = message_text.lower()
                for word in censorship_words:
                    if word.lower() in message_text_lower:
                        matching_user_ids.add(user_id)
                        break
            if matching_user_ids:
                return f"Найденные id пользователей: {', '.join(map(str, matching_user_ids))}"
            else:
                return "Совпадений не найдено."
    elif intent == "rat_bot":
        cursor.execute('SELECT user_id, message FROM messages WHERE user_id != ? ORDER BY id DESC', (user_id,))
        messages = cursor.fetchall()
        if messages:
            conversation1 = "\n".join([f"Пользователь {msg[0]}: {msg[1]}" for msg in messages if msg[1] is not None])
            return f"Сообщения других пользователей:\n{conversation1}"
        else:
            return "Нет сообщений от других пользователей."
    return "Извините, я не понимаю ваш запрос."



def main():
    application = ApplicationBuilder().token("8050637207:AAHkgXzJ4hB9zH9w6Otr-wiu-EQjPczmyK8").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.run_polling()


if __name__ == '__main__':
    main()
