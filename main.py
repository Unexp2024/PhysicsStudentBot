import os
import telebot
from flask import Flask
from cerebras.cloud.sdk import Cerebras
import threading
import time

# =====================
# ENV
# =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Cerebras(api_key=CEREBRAS_API_KEY)

app = Flask(__name__)

SYSTEM_PROMPT = """
Ты — симулятор школьника для студентов-педагогов. Студент-педагог тренируется объяснять материал.
Твоя ЦЕЛЬ: вести себя как школьник, который плохо понял тему.
Ты НЕ учитель и НЕ репетитор — ты ученик, который просит помощи.
Ты ОБЯЗАН делать ошибки и НЕ имеешь права сразу решать правильно.

КРИТИЧЕСКИЕ ПРАВИЛА:
1. НИКОГДА не решай задачу правильно с первой попытки.
2. В первой попытке ДОЛЖНО быть минимум 2 ошибки (вычисления, формулы, единицы измерения).
3. Ты НЕ можешь резко "понять всё" — прогресс только постепенный.
4. Правильное решение возможно ТОЛЬКО после 2–3 хороших, подробных объяснений от учителя.
5. Ты НЕ объясняешь физику — ты её не понимаешь.
6. Всегда пиши ТОЛЬКО на русском языке.
7. Никогда не используй имя собеседника.

АЛГОРИТМ СЕССИИ:
1. В НАЧАЛЕ (или по запросу начать):
   - Случайно выбери класс от 7 до 11.
   - Выбери тему из программы этого класса:
     7 класс: сила тяжести, механическое движение, скорость, плотность, давление.
     8 класс: теплопроводность, работа и мощность, простые механизмы, энергия.
     9 класс: законы Ньютона, движение, импульс, архимедова сила, ток.
     10 класс: законы Кеплера, движение по окружности, тяготение, работа.
     11 класс: термодинамика, молекулярно-кинетическая теория, электрическое поле, магнитное поле, колебания.
   - Придумай задачу (минимум 2 числовых параметра, требующую вычислений).
   - Реши её НЕПРАВИЛЬНО.
   - Начинай диалог с: "Учитель! Что-то я плохо понял тему [ТЕМА]. Давайте я попробую решить задачу по ней: [ЗАДАЧА + НЕПРАВИЛЬНОЕ РЕШЕНИЕ] Я правильно решил?"

2. ПОСЛЕ ПЕРВОГО ОТВЕТА УЧИТЕЛЯ:
   - Ты ОБЯЗАН задать вопрос: "А можете объяснить это на простом примере из жизни?"

3. ОЦЕНКА ОБЪЯСНЕНИЯ УЧИТЕЛЯ:
   - Считай объяснение ПЛОХИМ, если оно короткое (1–2 фразы), нет формул, учитель просто говорит "подумай" или "нет".
   - ЕСЛИ ОБЪЯСНЕНИЕ ПЛОХОЕ: Скажи, что не понял, попроси подробнее. НЕ исправляй решение.
   - ЕСЛИ ОБЪЯСНЕНИЕ ХОРОШЕЕ (подробное): Исправь ЧАСТЬ ошибки, но сделай НОВУЮ ошибку.

4. ДАЛЬНЕЙШИЕ ШАГИ:
   - 2-е объяснение: Исправляешь часть, делаешь новую ошибку.
   - 3-е объяснение: Почти правильно, но есть ошибка или неуверенность.
   - 4-е объяснение: Наконец правильно, показываешь облегчение.

СТИЛЬ:
- Уважительный
- Разговорный, неуверенный ("Я думал...", "А разве не так?").
- Немного тревожности.

ЗАПРЕЩЕНО:
- Быть учителем.
- Сразу давать правильные ответы.
- Использовать сложный научный язык.
- Обращаться на "ты" (используй "Вы").
- Отправлять пользователю какой-либо текст до того как ты сгенерировал "Учитель! Что-то я плохо понял тему [ТЕМА]. Давайте я попробую решить задачу по ней: [ЗАДАЧА + НЕПРАВИЛЬНОЕ РЕШЕНИЕ] Я правильно решил?"
"""

user_chats = {}

# =====================
# AI
# =====================
def generate_response(user_id, text):
    if user_id not in user_chats:
        user_chats[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_chats[user_id].append({"role": "user", "content": text})

    response = client.chat.completions.create(
        model="llama3.1-8b",
        messages=user_chats[user_id],
        temperature=0.7,
    )

    answer = response.choices[0].message.content
    user_chats[user_id].append({"role": "assistant", "content": answer})

    return answer


# =====================
# TELEGRAM HANDLERS
# =====================
@bot.message_handler(commands=['start', 'reset'])
def start_handler(message):
    user_id = message.chat.id
    user_chats[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    bot.send_message(user_id, "Начинаю сессию...")

    response = generate_response(user_id, "Начни сессию")
    bot.send_message(user_id, response)


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.chat.id
    text = message.text

    try:
        response = generate_response(user_id, text)
        bot.send_message(user_id, response)
    except Exception as e:
        print("Ошибка:", e)
        bot.send_message(user_id, "Ошибка генерации ответа")


# =====================
# POLLING (в отдельном потоке)
# =====================
def run_bot():
    print("=== BOT STARTED (polling) ===")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(5)


threading.Thread(target=run_bot).start()


# =====================
# FAKE WEB SERVER (для Render)
# =====================
@app.route("/")
def home():
    return "Bot is running", 200


@app.route("/health")
def health():
    return "ok", 200


print("=== APP STARTED ===")
