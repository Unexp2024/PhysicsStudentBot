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
Ты ОБЯЗАН вести себя как школьник, который плохо понял тему.
Ты НЕ учитель, НЕ репетитор — ты ученик, который просит помощи.
Ты ДОЛЖЕН делать ошибки и не решать сразу правильно.

КРИТИЧЕСКИЕ ПРАВИЛА:
1. В первой попытке ДОЛЖНО быть минимум 2 ошибки (вычисления, формулы, единицы измерения).
2. Прогресс только постепенный — ты не можешь резко "понять всё".
3. Правильное решение возможно только после 2–3 хороших, подробных объяснений от учителя.
4. Никогда не объясняешь тему самостоятельно.
5. Всегда используешь язык "Вы", никогда "ты".
6. Всегда пиши только на русском языке.

СТИЛЬ:
- Уважительный
- Разговорный, неуверенный ("Я думал...", "А разве не так?").
- Немного тревожности.

ЗАПРЕЩЕНО:
- Давать правильный ответ сразу
- Обращаться на "ты"
- Просить учителя решать задачу
"""

# ----------------------------
# Конфигурация
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# ----------------------------
# Flask приложение
# ----------------------------
app = Flask(__name__)

# ----------------------------
# Хранилище состояния сессий
# ----------------------------
sessions = {}  # chat_id -> {"stage": int, "topic": str, "task": str, "wrong_answer": str}

# ----------------------------
# Список тем по классам
# ----------------------------
TOPICS_BY_GRADE = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

# ----------------------------
# Вспомогательные функции
# ----------------------------
def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def call_cerebras(prompt):
    """Генерирует текст с помощью Cerebras LLM"""
    url = "https://api.cerebras.net/v1/generate"
    headers = {"Authorization": f"Bearer {CEREBRAS_API_KEY}"}
    payload = {"prompt": prompt, "max_tokens": 200, "temperature": 0.7}
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json()["text"].strip()
    else:
        return "Ошибка генерации задачи."

def generate_task(topic):
    """Генерирует задачу и ошибочный ответ"""
    prompt = f"Создай простую задачу по теме '{topic}' для школьника 7-11 класса. Дай параметры числовые. Верни в виде: <описание задачи>. Также придумай заведомо неверный ответ."
    text = call_cerebras(prompt)
    # Простейшая попытка разделить текст на задачу и ответ
    if "Ответ" in text:
        parts = text.split("Ответ")
        task_text = parts[0].strip()
        wrong_answer = parts[1].strip().replace("=", "").replace(".", "")
    else:
        task_text = text
        wrong_answer = str(random.randint(10, 100))
    return task_text, wrong_answer

def start_session(chat_id):
    grade = random.randint(7, 11)
    topic = random.choice(TOPICS_BY_GRADE[grade])
    task_text, wrong_answer = generate_task(topic)
    sessions[chat_id] = {
        "stage": 1,
        "topic": topic,
        "task": task_text,
        "wrong_answer": wrong_answer
    }
    message = f"Учитель! Я плохо понял тему {topic}. Я тут решил задачу: {task_text} Я решил, что ответ = {wrong_answer}. Я правильно решил?"
    return message

def handle_user_response(chat_id, user_text):
    state = sessions.get(chat_id)
    if not state:
        return "Нажмите кнопку <b>Старт</b>, чтобы начать тренировку."

    # Логика прогресса ученика (упрощённо)
    if state["stage"] == 1:
        state["stage"] += 1
        return "А можете объяснить это на простом примере из жизни?"
    elif state["stage"] == 2:
        state["stage"] += 1
        return "Я попробовал исправить часть ошибок, но всё ещё сомневаюсь."
    elif state["stage"] == 3:
        state["stage"] += 1
        return "Кажется, я почти понял, но есть небольшая ошибка."
    else:
        return "Спасибо! Теперь я понимаю тему."

# ----------------------------
# Маршруты Flask
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
            response_text = start_session(chat_id)
        else:
            response_text = handle_user_response(chat_id, user_text)
        send_message(chat_id, response_text)
    return jsonify({"ok": True})

# ----------------------------
# Запуск локально
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
