import os
import random
from flask import Flask, request
import telebot

# ========================
# Настройки
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")           # Ваш токен бота
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")       # Полный URL вашего веб-сервиса Render, куда Telegram будет слать обновления

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ========================
# Темы по классам
# ========================
CLASS_TOPICS = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"],
}

# ========================
# Генерация задачи
# ========================
def generate_task():
    grade = random.randint(7, 11)
    topic = random.choice(CLASS_TOPICS[grade])
    num1 = random.randint(1, 100)
    num2 = random.randint(1, 50)
    wrong_answer = f"{num1 * 2 + num2} (но я, наверное, ошибся)"
    return f"Учитель! Что-то я плохо понял тему {topic}. Давайте я попробую решить задачу по ней: \"В задаче есть два числа: {num1} и {num2}. Мой ответ: {wrong_answer}\". Я правильно решил?"

# ========================
# Webhook обработка
# ========================
@app.route("/webhook", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

# ========================
# Обработчики сообщений
# ========================
@bot.message_handler(commands=['start'])
def handle_start(message):
    task = generate_task()
    bot.send_message(message.chat.id, task)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    responses = [
        "А можете объяснить это на простом примере из жизни?",
        "Я всё ещё не совсем понял, можно ещё раз?",
        "Я попробую исправить часть ошибки, но не уверен...",
        "Хм… я всё равно сделал что-то не так, что именно?"
    ]
    bot.send_message(message.chat.id, random.choice(responses))

# ========================
# Запуск приложения
# ========================
if __name__ == "__main__":
    # Сбрасываем старый webhook и ставим новый
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    # Flask слушает порт Render
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
