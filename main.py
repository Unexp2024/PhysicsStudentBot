import os
import random
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

app = Flask(__name__)
student_state = {}  # chat_id -> {"stage": int, "topic": str, "task": str, "wrong_solution": str, "messages": [], "corrections": int}

# ----------------------------
# Telegram
# ----------------------------
def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

# ----------------------------
# Генерация задачи с разными типами ошибок
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
    error_type = random.choice(["calc", "unit", "logic"])

    if topic == "сила тяжести":
        task_text = f"Тело массой {a} кг падает с высоты {b} м. Найдите силу тяжести, действующую на тело."
        if error_type == "calc":
            wrong_solution = f"Я подумал, что F = {a} + {b} = {a+b} Н"
        elif error_type == "unit":
            wrong_solution = f"Я решил, что F = {a*b} кг"
        else:  # logic
            wrong_solution = f"Я решил, что F = {a} * 2 + {b} = {a*2+b} Н"

    elif topic == "механическое движение":
        task_text = f"Машина движется {a} м за {b} секунд. Найдите её скорость."
        if error_type == "calc":
            wrong_solution = f"Я решил, что v = {a} + {b} = {a+b} м/с"
        elif error_type == "unit":
            wrong_solution = f"Я подумал, что v = {a}/{b} км"
        else:
            wrong_solution = f"Я решил, что v = {a} * {b} = {a*b} м/с"

    elif topic == "скорость":
        task_text = f"Пешеход проходит {a} м за {b} секунд. Какова его скорость?"
        if error_type == "calc":
            wrong_solution = f"Я решил, что v = {a} * {b} = {a*b} м/с"
        elif error_type == "unit":
            wrong_solution = f"Я подумал, что v = {a} + {b} км/ч"
        else:
            wrong_solution = f"Я подумал, что v = {a}/{b} + 5 = {a//b + 5} м/с"

    elif topic == "плотность":
        task_text = f"Объём вещества {a} м³, масса {b} кг. Найдите плотность."
        if error_type == "calc":
            wrong_solution = f"Я решил, что ρ = {b}+{a} = {b+a} кг/м³"
        elif error_type == "unit":
            wrong_solution = f"Я подумал, что ρ = {b}/{a} г"
        else:
            wrong_solution = f"Я подумал, что ρ = {a}*{b} = {a*b} кг/м³"

    else:
        task_text = f"Параметры задачи: {a} и {b}. Найдите ответ."
        wrong_solution = f"Я решил, что ответ = {a+b}"

    return task_text, wrong_solution

# ----------------------------
# Инициализация ученика
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
        "messages": [],
        "corrections": 0
    }
    message = (f"Учитель! Что-то я плохо понял тему {topic}. "
               f"Я попытался решить задачу: {task_text} "
               f"{wrong_solution}. Я правильно решил?")
    return message

# ----------------------------
# Вызов Cerebras
# ----------------------------
def call_cerebras(messages):
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": "cerebras-chat-7b", "messages": messages, "max_new_tokens": 300}
    resp = requests.post(CEREBRAS_API_URL, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json().get("generated_text", "")
    return "Ошибка генерации ответа."

# ----------------------------
# Проверка релевантности
# ----------------------------
def is_response_relevant(topic, user_text):
    messages = [{"role": "system",
                 "content": f"Оцените, приближает ли это сообщение ученика к пониманию темы '{topic}'. Ответьте 'Да' или 'Нет'."},
                {"role": "user", "content": user_text}]
    result = call_cerebras(messages).strip().lower()
    return "да" in result

# ----------------------------
# Постепенное исправление ошибок
# ----------------------------
def update_wrong_solution(state):
    if state["corrections"] >= 2 and state["stage"] >= 3:
        old_solution = state["wrong_solution"]
        # случайное исправление ошибок
        if '+' in old_solution:
            state["wrong_solution"] = old_solution.replace('+', '*', 1)
        elif '*' in old_solution:
            state["wrong_solution"] = old_solution.replace('*', '/', 1)

# ----------------------------
# Генерация ответа ученика
# ----------------------------
def generate_student_response(chat_id, user_text):
    state = student_state.get(chat_id)
    if not state:
        return "Пожалуйста, нажмите кнопку 'Старт', чтобы начать."

    state["messages"].append({"role": "user", "content": user_text})
    if is_response_relevant(state["topic"], user_text):
        state["stage"] += 1
        state["corrections"] += 1

    update_wrong_solution(state)
    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + state["messages"]
    reply = call_cerebras(llm_messages)
    state["messages"].append({"role": "assistant", "content": reply})
    return reply

# ----------------------------
# Flask routes
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")
        if user_text.lower() in ["старт", "/start"]:
            response_text = init_student(chat_id)
        else:
            response_text = generate_student_response(chat_id, user_text)
        send_message(chat_id, response_text)
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
