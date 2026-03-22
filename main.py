import os
import random
from flask import Flask, request
import telebot

# =======================
# Настройки бота
# =======================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Установите TELEGRAM_BOT_TOKEN в переменных окружения!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# =======================
# Темы по классам
# =======================
CLASSES_TOPICS = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

# =======================
# Функции генерации задач
# =======================
def generate_task_and_wrong_solution():
    # Случайный класс и тема
    class_num = random.randint(7, 11)
    topic = random.choice(CLASSES_TOPICS[class_num])
    
    # Простая задача с двумя числами
    a = random.randint(1, 100)
    b = random.randint(1, 100)
    
    # Придумать текст задачи
    task_text = f"Эта задача по теме {topic}: два числа {a} и {b}. Что с ними произойдет?"

    # Неправильное решение: случайная ошибка
    wrong_answer = f"Я думаю, что результат равен {a + b + random.randint(1,10)} (я мог ошибиться)."

    return class_num, topic, task_text, wrong_answer

def make_bot_message():
    class_num, topic, task, wrong_answer = generate_task_and_wrong_solution()
    return f"Учитель! Что-то я плохо понял тему {topic}. Давайте я попробую решить задачу по ней: {task} {wrong_answer} Я правильно решил?"

# =======================
# Обработчик webhook
# =======================
@app.route("/webhook", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

# =======================
# Простая проверка health
# =======================
@app.route("/health")
def health():
    return "OK", 200

# =======================
# Обработчик команды /start
# =======================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, make_bot_message())

# =======================
# Запуск на локальном сервере (для теста)
# =======================
if __name__ == "__main__":
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
