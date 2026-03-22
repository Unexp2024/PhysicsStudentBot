import os
import random
from flask import Flask, request
import telebot

# ======== Настройки ========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ======== Темы по классам ========
classes_topics = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

# ======== Школьник-состояние ========
user_states = {}  # chat_id -> состояние {"step": int, "grade": int, "topic": str, "task": str, "solution": str}

def generate_task_and_wrong_solution():
    grade = random.choice(list(classes_topics.keys()))
    topic = random.choice(classes_topics[grade])
    
    # Случайная задача
    a = random.randint(2, 20)
    b = random.randint(5, 50)
    task = f"Объект имеет параметры {a} и {b}. Считайте что-то по теме {topic}."
    
    # Неправильное решение с 2 ошибками
    wrong_solution = f"Я думаю, что ответ равен {a*b/2}, но может быть {a+b}."
    
    return grade, topic, task, wrong_solution

def next_step_response(state):
    step = state["step"]
    a, b = random.randint(2, 20), random.randint(5, 50)
    
    if step == 0:
        # Первое сообщение с ошибками
        response = f"Учитель! Что-то я плохо понял тему {state['topic']}. " \
                   f"Давайте я попробую решить задачу по ней: {state['task']} {state['solution']} Я правильно решил?"
        state["step"] += 1
        return response
    elif step == 1:
        # После первого объяснения — просит пример
        response = "А можете объяснить это на простом примере из жизни?"
        state["step"] += 1
        return response
    elif step == 2:
        # Исправляет часть ошибки, делает новую
        response = f"Я немного понял, может быть ответ {a+b}, но я всё ещё сомневаюсь..."
        state["step"] += 1
        return response
    elif step == 3:
        # Почти правильно, но не полностью
        response = f"Похоже я почти понял, может быть {a*b-5}? Но не уверен..."
        state["step"] += 1
        return response
    else:
        # Правильный ответ
        response = f"Теперь кажется я понял! Ответ должен быть {a*b}."
        state["step"] = 0  # сброс на новую задачу
        # Генерируем новую задачу
        grade, topic, task, solution = generate_task_and_wrong_solution()
        state.update({"grade": grade, "topic": topic, "task": task, "solution": solution})
        return response

# ======== Эндпоинт health ========
@app.route("/health")
def health():
    return "OK", 200

# ======== Эндпоинт webhook ========
@app.route("/webhook", methods=["POST"])
def webhook():
    json_data = request.get_json()
    bot.process_new_updates([telebot.types.Update.de_json(json_data)])
    return "", 200

# ======== Обработка сообщений ========
@bot.message_handler(commands=['start'])
def handle_start(message):
    grade, topic, task, solution = generate_task_and_wrong_solution()
    user_states[message.chat.id] = {"step": 0, "grade": grade, "topic": topic, "task": task, "solution": solution}
    response = next_step_response(user_states[message.chat.id])
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    if message.chat.id not in user_states:
        # Если пользователь новый, инициализируем состояние
        grade, topic, task, solution = generate_task_and_wrong_solution()
        user_states[message.chat.id] = {"step": 0, "grade": grade, "topic": topic, "task": task, "solution": solution}
    state = user_states[message.chat.id]
    response = next_step_response(state)
    bot.send_message(message.chat.id, response)

# ======== Настройка webhook ========
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ======== Запуск Flask ========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
