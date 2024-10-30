import spacy
import numpy as np
from sklearn.cluster import KMeans
from telegram import Update
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from telegram.ext import ContextTypes

from app.database import cursor, conn

# Загрузка модели для обработки естественного языка (NLP)
nlp = spacy.load("ru_core_news_sm")

history = []


# Обработчик входящих сообщений
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from main import client
    user_id = update.message.from_user.id  # Получение ID пользователя
    username = update.message.from_user.username  # Получение имени пользователя
    message = update.message.text  # Получение текста сообщения

    # Сохранение пользователя в базе данных, если он новый
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)
    ''', (user_id, username))
    conn.commit()

    # Сохранение сообщения в базе данных
    cursor.execute('''
    INSERT INTO messages (user_id, message) VALUES (?, ?)
    ''', (user_id, message))
    conn.commit()

    # Обработка сообщения для определения намерения
    intent = handle_message_enter(message)
    if intent is not None:
        response = process_intent(intent, user_id)  # Обработка намерения
        await update.message.reply_text(response)  # Ответ пользователю
    else:
        # Создание шаблона подсказки для OpenAI
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Вы — высококлассный технический писатель."),
            ("user", "{input}")
        ])
        # Создание цепочки обработки
        chain = prompt | client | StrOutputParser()
        # Хранение истории сообщений
        history.append({"role": "user", "content": message})
        context_input = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        response = chain.invoke({"input": context_input})  # Получение ответа от OpenAI
        # Добавление ответа бота в историю
        history.append({"role": "bot", "content": response})
        await update.message.reply_text(response)  # Ответ пользователю


# Функция для обработки входящего сообщения и определения его намерения
def handle_message_enter(message):
    intents = {
        "last_conversation": ["последний разговор", "предыдущие сообщения", "последнее общение", "все диалоги", "мои последнии сообщения"],
        "user_list": ["список пользователей", "со мной", "общались с тобой", "все юзеры, ", "все кто", "кто с тобой общался?", "еще общался"],
        "frequent_questions": ["часто", "задаваемые", "частые вопросы", "часто спрашивают", "что чаще", "что чаще спрашивают",
                               "что задают", "самый частый","чаще всего задают"],
        "censorship": ["censorship_bot"],
        "request_oder_users": ["другие", "другие пользователи", "запросы других", "других юзеров", "вопросы других", "о чем", "диалоги других"]
    }

    doc = nlp(message.lower())  # Обработка сообщения с помощью NLP

    # Проверка, соответствует ли сообщение какому-либо намерению
    for intent, keywords in intents.items():
        if any(keyword in doc.text for keyword in keywords):
            return intent
    return None  # Если намерение не найдено


# Функция для обработки намерения и формирования ответа
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
        kmeans = KMeans(n_clusters=10)  # Кластеризация сообщений
        kmeans.fit(vectors)
        labels, counts = np.unique(kmeans.labels_, return_counts=True)
        popular_cluster_index = labels[np.argmax(counts)]  # Находим самый популярный кластер
        cluster_questions = [messages_avr[i][0] for i in range(len(messages_avr)) if
                             kmeans.labels_[i] == popular_cluster_index]
        return f"Самый популярный вопрос: {cluster_questions[0]}"
    elif intent == "censorship":
        cursor.execute('SELECT id, user_id, message FROM messages ORDER BY id DESC')
        messages = cursor.fetchall()
        with open("censorship.txt", 'r', encoding="utf-8") as file:
            censorship_words = file.read().splitlines()  # Чтение слов для цензуры
            matching_user_ids = set()
            for message in messages:
                message_id, user_id, message_text = message
                message_text_lower = message_text.lower()
                for word in censorship_words:
                    if word.lower() in message_text_lower:
                        matching_user_ids.add(user_id)  # Сохраняем ID пользователей с неподобающими сообщениями
                        break
            if matching_user_ids:
                return f"Найденные id пользователей: {', '.join(map(str, matching_user_ids))}"
            else:
                return "Совпадений не найдено."
    elif intent == "request_oder_users":
        cursor.execute('SELECT user_id, message FROM messages WHERE user_id != ? ORDER BY id DESC', (user_id,))
        messages = cursor.fetchall()
        if messages:
            conversation1 = "\n".join([f"Пользователь {msg[0]}: {msg[1]}" for msg in messages if msg[1] is not None])
            return f"Сообщения других пользователей:\n{conversation1}"
        else:
            return "Нет сообщений от других пользователей."
    return "Извините, я не понимаю ваш запрос."  # Если намерение не распознано
