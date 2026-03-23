import os
import requests
from flask import Flask, request, jsonify

# ----------------------------
# SYSTEM PROMPT
# ----------------------------
SYSTEM_PROMPT = """Ты — симулятор школьника для студентов-педагогов.
(оставь свой полный промт как есть, я сократил тут для читаемости)
"""

# ----------------------------
# CONFIG
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# ----------------------------
# APP
# ----------------------------
app = Flask(__name__)

# ХРАНИМ СОСТОЯНИЕ
user_states = {}

# ----------------------------
# HEALTH
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ----------------------------
# TELEGRAM SEND
# ----------------------------
def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

# ----------------------------
# CEREBRAS CALL
# ----------------------------
def ask_cerebras(messages):
    url = "https://api.cerebras.ai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama3.1-8b",
        "messages": messages,
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        print("CEREBRAS ERROR:", e)
        return "Учитель! Что-то я совсем запутался… Можно ещё раз объяснить?"

# ----------------------------
# GENERATION LOGIC
# ----------------------------
def generate_response(chat_id, user_text):
    state = user_states.get(chat_id, {
        "step": 0,
        "history": []
    })

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # история
    for msg in state["history"]:
        messages.append(msg)

    # добавляем новое сообщение учителя
    messages.append({"role": "user", "content": user_text})

    # ВАЖНО: первый шаг принудительно старт
    if state["step"] == 0:
        messages.append({
            "role": "system",
            "content": "Сейчас НАЧАЛО занятия. Сгенерируй первое сообщение строго по правилам (с задачей и ошибками)."
        })

    response = ask_cerebras(messages)

    # обновляем историю
    state["history"].append({"role": "user", "content": user_text})
    state["history"].append({"role": "assistant", "content": response})

    state["step"] += 1
    user_states[chat_id] = state

    return response

# ----------------------------
# WEBHOOK
# ----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")

        # СРАЗУ отвечаем Telegram (важно!)
        send_message(chat_id, "⏳ Думаю...")

        try:
            if user_text.lower() in ["старт", "/start", "начать"]:
                user_states[chat_id] = {"step": 0, "history": []}
                response = generate_response(chat_id, "Начнём занятие")
            else:
                response = generate_response(chat_id, user_text)

            send_message(chat_id, response)

        except Exception as e:
            print("ERROR:", e)
            send_message(chat_id, "Учитель… у меня что-то не получается 😥")

    return jsonify({"ok": True})

# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
