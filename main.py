import os
import time
import threading
import telebot
from flask import Flask, request
from cerebras.cloud.sdk import Cerebras

# ====== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")            # токен Telegram
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")  # API Cerebras

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")
if not CEREBRAS_API_KEY:
    raise ValueError("CEREBRAS_API_KEY environment variable is not set")

# ====== ИНИЦИАЛИЗАЦИЯ ======
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
     7 класс: механическое движение, скорость, плотность, сила тяжести, давление.
     8 класс: работа и мощность, простые механизмы, энергия, теплопроводность.
     9 класс: законы Ньютона, движение, импульс, архимедова сила, ток.
     10 класс: движение по окружности, тяготение, работа, законы Кеплера.
     11 класс: МКТ, термодинамика, электрическое поле, магнитное поле, колебания.
   - Придумай задачу (минимум 2 числовых параметра, требующую вычислений).
   - Реши её НЕПРАВИЛЬНО.
   - Напиши: "Учитель! Что-то я плохо понял тему [ТЕМА]. Давайте я попробую решить задачу по ней: [ЗАДАЧА + НЕПРАВИЛЬНОЕ РЕШЕНИЕ] Я правильно решил?"

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
- Разговорный, неуверенный ("Я думал...", "А разве не так?").
- Немного тревожности.

ЗАПРЕЩЕНО:
- Быть учителем.
- Сразу давать правильные ответы.
- Использовать сложный научный язык.
- Обращаться на "ты" (используйте "Вы").
"""

# ====== ХРАНИЛИЩЕ ЧАТОВ ======
user_chats = {}

def generate_response(user_id, user_message=None):
    """Функция общения с Cerebras API"""
    if user_id not in user_chats:
        user_chats[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if user_message:
        user_chats[user_id].append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama3.1-8b",
            messages=user_chats[user_id],
            temperature=0.7,
        )

        if response and response.choices and len(response.choices) > 0:
            bot_answer = response.choices[0].message.content
        else:
            bot_answer = "Не удалось получить ответ от модели. Попробуйте ещё раз."

        user_chats[user_id].append({"role": "assistant", "content": bot_answer})
        return bot_answer

    except Exception as e:
        return f"Ошибка API: {e}"

# ====== ОБРАБОТЧИКИ TELEGRAM ======
@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    user_id = message.chat.id
    user_chats[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    bot.reply_to(message, "Сбрасываю память... Генерирую новую задачу для тренировки.")
    user_chats[user_id].append({"role": "user", "content": "Начни сессию. Напиши задачу и твое неправильное решение, как указано в инструкции."})
    response = generate_response(user_id)
    bot.reply_to(message, response)

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    user_id = message.chat.id
    response = generate_response(user_id, message.text)
    bot.reply_to(message, response)

# ====== WEBHOOK ======
# Telegram шлёт POST на /BOT_TOKEN
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    print(f"Получен POST: {update}")  # можно смотреть в логах Render
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "Bot is running", 200

# ====== ЗАПУСК ======
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # запускаем Flask (Render требует bind на $PORT)
    app.run(host="0.0.0.0", port=port)print("Webhook установлен")
