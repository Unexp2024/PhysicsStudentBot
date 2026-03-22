import os
import threading
from flask import Flask
import telebot
import random

# ===== Настройки бота =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# ===== Настройки школьника =====
CLASSES = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

# Хранение состояния сессии: {chat_id: {"step": 1, "cls": 9, "topic": "...", "a": ..., "b": ..., "current_error": 2}}
sessions = {}

def generate_task(chat_id):
    cls = random.randint(7, 11)
    topic = random.choice(CLASSES[cls])
    a = random.randint(10, 200)
    b = random.randint(1, 20)
    wrong_result = f"{a + b*2} (думаю это правильно, но может ошибаюсь)"
    sessions[chat_id] = {"step": 1, "cls": cls, "topic": topic, "a": a, "b": b, "current_error": 2}
    return f"Учитель! Что-то я плохо понял тему {topic}. Давайте я попробую решить задачу по ней: " \
           f"Если есть параметры {a} и {b}, то мой ответ: {wrong_result}. Я правильно решил?"

def process_teacher_response(chat_id, message):
    session = sessions.get(chat_id)
    if not session:
        return "Пожалуйста, сначала используйте /start для новой задачи."
    
    step = session["step"]
    a, b = session["a"], session["b"]
    topic = session["topic"]
    errors = session["current_error"]
    
    # Оценка объяснения: короткое = плохое, длинное = хорошее
    if len(message.text.split()) <= 5:
        response = f"Я всё ещё не понял, можете объяснить подробнее?"
        # Ошибки не меняются
    else:
        # Исправляем часть ошибки, но оставляем новую
        errors = max(0, errors - 1)
        session["current_error"] = errors
        if errors == 0:
            response = f"Теперь я почти понял! Мой новый ответ: {a + b}. Думаю, это правильно?"
        else:
            wrong_result = f"{a + b + errors} (я немного исправил, но всё ещё не уверен)"
            response = f"Я попробовал исправить: {wrong_result}. А можете объяснить ещё?"
    
    session["step"] += 1
    return response

# ===== Обработчик сообщений =====
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.lower()
    chat_id = message.chat.id
    if text == "/start":
        bot.reply_to(message, generate_task(chat_id))
    else:
        bot.reply_to(message, process_teacher_response(chat_id, message))

# ===== Функция запуска polling =====
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

# ===== Flask сервер для Render =====
app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
