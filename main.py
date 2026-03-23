import os
import random
import json
import requests
from flask import Flask, request, jsonify

# ----------------------------
# Системный промпт
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
8. Обращайся на "Вы".

СТИЛЬ:
- Уважительный
- Разговорный, неуверенный ("Я думал...", "А разве не так?").
- Немного тревожности.

ЗАПРЕЩЕНО:
- Быть учителем.
- Сразу давать правильные ответы.
- Использовать сложный научный язык.
- Предлагать учителю что-либо решать.
"""

# ----------------------------
# Конфигурация
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
CEREBRAS_API_URL = "https://api.cerebras.net/v1/generate"

# ----------------------------
# Flask приложение
# ----------------------------
app = Flask(__name__)

# ----------------------------
# Состояние ученика
# ----------------------------
student_state = {}  # chat_id -> {"stage": int, "topic": str, "task": str, "wrong_solution": str, "messages": []}

# ----------------------------
# Telegram
# ----------------------------
def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

# ----------------------------
# Генерация учебной задачи с ошибкой
# ----------------------------
TOPICS = {
    "7": ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    "8": ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    "9": ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    "10": ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    "11": ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

def generate_task_and_wrong_solution(topic):
    a = random.randint(10, 50)
    b = random.randint(2, 20)

    if topic == "сила тяжести":
        task_text = f"Тело массой {a} кг падает с высоты {b} м. Найдите силу тяжести, действующую на тело."
        wrong_solution = f"Я подумал, что F = {a} + {b} = {a+b} Н"
    elif topic == "механическое движение":
        task_text = f"Машина движется {a} м за {b} секунд. Найдите её скорость."
        wrong_solution = f"Я подумал, что v = {a} + {b} = {a+b} м/с"
    elif topic == "скорость":
        task_text = f"Пешеход проходит {a} м за {b} секунд. Какова его скорость?"
        wrong_solution = f"Я решил, что v = {a} * {b} = {a*b} м/с"
    elif topic == "плотность":
        task_text = f"Объём вещества {a} м³, масса {b} кг. Найдите плотность."
        wrong_solution = f"Я решил, что ρ = {b} + {a} = {b+a} кг/м³"
    elif topic == "давление":
        task_text = f"Сила {a} Н действует на площадь {b} м². Найдите давление."
        wrong_solution = f"Я подумал, что P = {a} + {b} = {a+b} Па"
    else:
        task_text = f"Параметры задачи: {a} и {b}. Найдите ответ."
        wrong_solution = f"Я решил, что ответ = {a+b}"

    return task_text, wrong_solution

# ----------------------------
# Инициализация ученика (старт)
# ----------------------------
def init_student(chat_id):
    grade = random.randint(7, 11)
    topic = random.choice(TOPICS[str(grade)])
    task_text, wrong_solution = generate_task_and_wrong_solution(topic)

    student_state[chat_id] = {
        "stage": 1,
        "topic": topic,
        "task": task_text,
        "wrong_solution": wrong_solution,
        "messages": []
    }

    message = (f"Учитель! Что-то я плохо понял тему {topic}. "
               f"Я попытался решить задачу: {task_text} "
               f"{wrong_solution}. Я правильно решил?")
    return message

# ----------------------------
# Вызов Cerebras LLM
# ----------------------------
def call_cerebras(messages):
    """
    messages: список dict {role: "system/user/assistant", content: str}
    """
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "cerebras-chat-7b",
        "messages": messages,
        "max_new_tokens": 300
    }
    resp = requests.post(CEREBRAS_API_URL, headers=headers, json=payload)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("generated_text", "")
    else:
        return "Ошибка генерации ответа."

# ----------------------------
# Генерация ответа ученика через LLM
# ----------------------------
def generate_student_response(chat_id, user_text):
    state = student_state.get(chat_id)
    if not state:
        return "Пожалуйста, нажмите кнопку 'Старт', чтобы начать."

    # Сохраняем сообщение студента
    state["messages"].append({"role": "user", "content": user_text})

    # Подготовка сообщений для LLM
    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in state["messages"]:
        llm_messages.append(m)

    # Генерация ответа
    reply = call_cerebras(llm_messages)

    # Сохраняем ответ бота
    state["messages"].append({"role": "assistant", "content": reply})

    # Прогрессируем стадию
    state["stage"] += 1

    return reply

# ----------------------------
# Маршрут Render health check
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ----------------------------
# Webhook для Telegram
# ----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")

        # Старт
        if user_text.lower() in ["старт", "/start"]:
            response_text = init_student(chat_id)
        else:
            response_text = generate_student_response(chat_id, user_text)

        send_message(chat_id, response_text)

    return jsonify({"ok": True})

# ----------------------------
# Запуск локально
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
