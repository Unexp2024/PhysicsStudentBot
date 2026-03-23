import os
import random
import requests
from flask import Flask, request, jsonify

# ----------------------------
# CONFIG
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)
sessions = {}

# ----------------------------
# TOPICS
# ----------------------------
TOPICS_BY_GRADE = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "электрическое поле", "магнитное поле", "колебания"]
}

# ----------------------------
# TELEGRAM
# ----------------------------
def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

# ----------------------------
# CEREBRAS CALL
# ----------------------------
def call_cerebras(prompt):
    url = "https://api.cerebras.net/v1/generate"
    headers = {"Authorization": f"Bearer {CEREBRAS_API_KEY}"}
    payload = {
        "prompt": prompt,
        "max_tokens": 250,
        "temperature": 0.7
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.json().get("text", "")
    except:
        return ""

# ----------------------------
# VALIDATION (КЛЮЧЕВОЕ!)
# ----------------------------
def fix_task(text):
    text_lower = text.lower()

    # если нет вопроса → добавляем
    if "найдите" not in text_lower and "определите" not in text_lower:
        text = text.strip() + "\nНайдите искомую величину."

    # если нет "Я подумал" → добавляем ученическое решение-заглушку
    if "я" not in text_lower:
        text += "\nЯ подумал, что нужно просто сложить числа, поэтому получил ответ 10."

    return text.strip()

# ----------------------------
# GENERATE TASK
# ----------------------------
def generate_task(topic):
    prompt = f"""
Сгенерируй школьную задачу по физике на тему "{topic}".

СТРОГО КАК В УЧЕБНИКЕ:

1. Краткое условие (1-2 предложения)
2. Чёткий вопрос: "Найдите..." или "Определите..."
3. Неправильное решение ученика

ТРЕБОВАНИЯ:
- Минимум 2 числовых параметра
- Без лишней болтовни
- Реалистичный школьный стиль
- Решение ученика должно быть с ошибками
- Ученик пишет неуверенно

ФОРМАТ:
<условие>
<вопрос>
Я подумал, что ...

НЕ ПИШИ правильный ответ
"""

    raw = call_cerebras(prompt)
    return fix_task(raw)

# ----------------------------
# START SESSION
# ----------------------------
def start_session(chat_id):
    grade = random.randint(7, 11)
    topic = random.choice(TOPICS_BY_GRADE[grade])

    task = generate_task(topic)

    sessions[chat_id] = {
        "stage": 1,
        "topic": topic
    }

    return (
        f"Учитель! Я плохо понял тему {topic}. "
        f"Я тут решил задачу:\n{task}\n"
        f"Я правильно решил?"
    )

# ----------------------------
# PROGRESSION (упрощённо)
# ----------------------------
def handle_response(chat_id, user_text):
    state = sessions.get(chat_id)

    if not state:
        return "Нажмите Старт."

    stage = state["stage"]

    if stage == 1:
        state["stage"] = 2
        return "А можете объяснить это на простом примере из жизни?"

    elif stage == 2:
        state["stage"] = 3
        return "Я вроде понял часть, но всё равно путаюсь..."

    elif stage == 3:
        state["stage"] = 4
        return "Кажется, я почти понял, но не уверен..."

    else:
        return "Ой, теперь вроде понял! Спасибо!"

# ----------------------------
# ROUTES
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").lower()

        if text in ["старт", "/start"]:
            reply = start_session(chat_id)
        else:
            reply = handle_response(chat_id, text)

        send_message(chat_id, reply)

    return jsonify({"ok": True})

# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
