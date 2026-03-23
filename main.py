import os
import random
import json
import requests
from flask import Flask, request, jsonify

# ----------------------------
# Системный промт
# ----------------------------
SYSTEM_PROMPT = """
Ты — виртуальный школьник для студентов-педагогов. Студент тренируется объяснять материал.
ЦЕЛЬ: вести себя как ученик, который плохо понял тему.
НЕЛЬЗЯ: быть учителем, сразу давать правильный ответ, обращаться на "ты" (только Вы).
ДОЛЖНО быть: минимум 2 ошибки в первой попытке, постепенное понимание после нескольких объяснений.
Стиль: уважительный, разговорный, неуверенный, немного тревожный.
"""

# ----------------------------
# Конфигурация
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# ----------------------------
# Flask приложение
# ----------------------------
app = Flask(__name__)

# Простейший маршрут для Render health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ----------------------------
# Функции для Telegram
# ----------------------------
def send_message(chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

# ----------------------------
# LLM вызов
# ----------------------------
def call_llm(prompt):
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"prompt": prompt, "max_tokens": 300}
    response = requests.post("https://api.cerebras.net/v1/generate", headers=headers, json=data)
    return response.json()["text"]

# ----------------------------
# Состояние учеников
# ----------------------------
STUDENT_STATE = {}  # chat_id -> state dict

def init_student(chat_id):
    # Выбираем случайный класс и тему
    class_topic = {
        7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
        8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
        9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
        10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
        11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
    }
    grade = random.randint(7, 11)
    topic = random.choice(class_topic[grade])
    # Случайная задача с двумя числовыми параметрами
    a, b = random.randint(1, 50), random.randint(1, 50)
    task = f"Пример задачи: параметр1={a}, параметр2={b}. Попробуйте решить."
    # Неправильное решение (для первой попытки)
    wrong_solution = f"Я думаю, ответ = {a+b+random.randint(1,5)}"
    STUDENT_STATE[chat_id] = {
        "grade": grade,
        "topic": topic,
        "task": task,
        "stage": 0,
        "last_student_msg": "",
        "last_bot_msg": f"Учитель! Что-то я плохо понял тему {topic}. {task} {wrong_solution}. Я правильно решил?"
    }
    return STUDENT_STATE[chat_id]["last_bot_msg"]

# ----------------------------
# Оценка сообщений студента per se
# ----------------------------
def assess_student_message(student_text, topic):
    prompt = f"""
    Тема ученика: {topic}
    Сообщение студента: "{student_text}"

    Оцени:
    1. По теме ли сообщение? Ответ: True/False
    2. Помогает ли оно ученику лучше понять тему (поясняет, исправляет ошибку, даёт пример)? Ответ: True/False
    Дай ответ в формате: True, True
    """
    try:
        response = call_llm(prompt)
        relevant, helpful = response.strip().split(",")
        return relevant.strip() == "True", helpful.strip() == "True"
    except Exception:
        return False, False

# ----------------------------
# Генерация ответа ученика
# ----------------------------
def generate_student_response(chat_id, student_msg):
    state = STUDENT_STATE.get(chat_id)
    if not state:
        return init_student(chat_id)

    # Оценка сообщения студента
    relevant, helpful = assess_student_message(student_msg, state["topic"])
    if not relevant:
        bot_msg = "Учитель! Я не совсем понял, о чём Вы. Можете объяснить ещё раз?"
    elif helpful:
        state["stage"] += 1
        # Новая попытка с небольшой ошибкой
        a, b = random.randint(1, 50), random.randint(1, 50)
        new_wrong = f"Я думаю, ответ = {a+b+random.randint(1,5)}"
        bot_msg = f"Учитель! Попробовал ещё раз: {state['task']} {new_wrong}. Я правильно?"
    else:
        bot_msg = "Учитель! Я вроде понял, но всё равно что-то не выходит. Можете объяснить подробнее?"

    state["last_student_msg"] = student_msg
    state["last_bot_msg"] = bot_msg
    return bot_msg

# ----------------------------
# Webhook для Telegram
# ----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")
        response_text = generate_student_response(chat_id, user_text)
        send_message(chat_id, response_text)
    return jsonify({"ok": True})

# ----------------------------
# Запуск локально для отладки
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
