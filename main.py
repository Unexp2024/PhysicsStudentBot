import os
import random
import json
import requests
from flask import Flask, request, jsonify

# ----------------------------
# Системный промт
# ----------------------------
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
"""

# ----------------------------
# Конфигурация
# ----------------------------
TOKEN = os.environ.get("TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# ----------------------------
# Flask приложение
# ----------------------------
app = Flask(__name__)

# Простая память диалогов: chat_id → история
dialogs = {}

# ----------------------------
# Темы и задачи
# ----------------------------
CLASSES = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

# Генерация задачи с ошибкой
def generate_task_with_mistake(class_number, topic):
    # два случайных числа для задачи
    a = random.randint(2, 20)
    b = random.randint(5, 50)
    # простая "ошибочная формула"
    if "скорость" in topic:
        # ошибка: умножение неверное
        value = a * b + random.randint(1, 5)  # ошибка
        task_text = f"v = {a} * {b} + {random.randint(1,5)} = {value} м/с"
    elif "сила" in topic:
        value = a + b + random.randint(1,10)
        task_text = f"F = {a} + {b} + {random.randint(1,10)} = {value} Н"
    elif "давление" in topic:
        value = a / b + random.randint(1,5)
        task_text = f"P = {a} / {b} + {random.randint(1,5)} = {value} Па"
    else:
        value = a + b  # универсальная ошибка
        task_text = f"{topic}: {a} + {b} = {value}"
    return task_text

# ----------------------------
# Логика генерации ответа ученика
# ----------------------------
def generate_student_response(chat_id, user_text):
    # Инициализация диалога
    if chat_id not in dialogs:
        # Случайный класс и тема
        class_number = random.randint(7, 11)
        topic = random.choice(CLASSES[class_number])
        task = generate_task_with_mistake(class_number, topic)
        dialogs[chat_id] = {
            "step": 1,
            "class": class_number,
            "topic": topic,
            "last_task": task
        }
        return f"Учитель! Что-то я плохо понял тему {topic}. Давайте я попробую решить задачу по ней: {task} Я правильно решил?"

    # Обработка следующих шагов
    dialog = dialogs[chat_id]
    step = dialog["step"]
    topic = dialog["topic"]

    if step == 1:
        response = "А можете объяснить это на простом примере из жизни?"
        dialog["step"] += 1
    elif step == 2:
        # частично исправляем ошибку, делаем новую
        task = dialog["last_task"]
        new_task = task.replace("м/с", "км/ч") if "м/с" in task else task
        response = f"Я подумал и вроде исправил часть: {new_task}, но всё равно что-то не так?"
        dialog["last_task"] = new_task
        dialog["step"] += 1
    elif step == 3:
        response = f"Учитель, я почти понял, но я сделал маленькую ошибку в {topic}."
        dialog["step"] += 1
    else:
        response = f"Кажется, теперь я понял правильно задачу по {topic}! Спасибо!"
        # очищаем историю после полного понимания
        dialogs.pop(chat_id)

    return response

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
# Отправка сообщений
# ----------------------------
def send_message(chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

# ----------------------------
# Простейший маршрут для Render health check
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ----------------------------
# Запуск локально для отладки
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
