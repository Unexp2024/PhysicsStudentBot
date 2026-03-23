import os
import requests
from flask import Flask, request, jsonify

# ----------------------------
# CONFIG
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)

# ----------------------------
# HEALTH
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

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
def call_llm(messages):
    url = "https://api.cerebras.ai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama3.1-8b",
        "messages": messages,
        "temperature": 0.9,
        "max_tokens": 500
    }

    r = requests.post(url, headers=headers, json=payload)
    return r.json()["choices"][0]["message"]["content"]

# ----------------------------
# VALIDATION
# ----------------------------
def is_valid_task(text):
    return (
        "ЗАДАЧА:" in text and
        "ЧТО НАЙТИ:" in text and
        "РЕШЕНИЕ УЧЕНИКА:" in text
    )

# ----------------------------
# GENERATE TASK (WITH RETRY)
# ----------------------------
def generate_task():

    for _ in range(3):

        messages = [
            {
                "role": "system",
                "content": """
Ты школьник, который плохо понимает физику.

Сгенерируй ОДНУ задачу строго в формате:

ЗАДАЧА:
(полное условие с числами)

ЧТО НАЙТИ:
(что нужно вычислить)

РЕШЕНИЕ УЧЕНИКА:
(НЕПРАВИЛЬНОЕ решение с минимум 2 ошибками)

ТРЕБОВАНИЯ:
- 7–11 класс
- обязательно числа
- минимум 2 ошибки
- ученик путается
- НЕ давай правильный ответ
"""
            }
        ]

        text = call_llm(messages)

        if is_valid_task(text):
            return text

    # fallback если LLM тупит
    return """ЗАДАЧА:
Тело массой 2 кг движется со скоростью 3 м/с.

ЧТО НАЙТИ:
Импульс тела.

РЕШЕНИЕ УЧЕНИКА:
Я думаю, импульс = 2 + 3 = 6 кг·м/с.
Наверное, надо было сложить.
"""

# ----------------------------
# START MESSAGE
# ----------------------------
def build_start_message(task_text):
    return f"""Учитель! Я плохо понял тему. Я тут решил задачу:

{task_text}

Я правильно решил?"""

# ----------------------------
# WEBHOOK
# ----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text.lower() == "/start":
            task = generate_task()
            msg = build_start_message(task)
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "Я не понял объяснение... Можете объяснить подробнее?")

    return jsonify({"ok": True})

# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
