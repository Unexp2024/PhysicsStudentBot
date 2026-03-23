import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# =========================
# MEMORY (state)
# =========================
sessions = {}

# =========================
# TELEGRAM
# =========================
def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })


# =========================
# LLM CALL (CEREBRAS)
# =========================
def call_llm(messages):
    try:
        response = requests.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3.1-8b",
                "messages": messages,
                "temperature": 0.7
            },
            timeout=20
        )

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        print("LLM ERROR:", e)
        return None


# =========================
# VALIDATE TASK (LLM)
# =========================
def validate_task(task_text):
    messages = [
        {
            "role": "system",
            "content": """
Ты проверяешь задачу по физике.

Ответь строго:
VALID или INVALID

Критерии:
- есть все необходимые данные
- задача решаема
- нет пропущенных величин
"""
        },
        {"role": "user", "content": task_text}
    ]

    result = call_llm(messages)
    return result and "VALID" in result


# =========================
# GENERATE TASK
# =========================
def generate_task():
    for _ in range(5):
        messages = [
            {
                "role": "system",
                "content": """
Сгенерируй задачу по школьной физике.

СТРОГО:
1. Сначала "ЗАДАЧА:"
(полное условие с числами)

2. Потом "ЧТО НАЙТИ:"
(одна величина)

3. Потом "РЕШЕНИЕ УЧЕНИКА:"
(НЕПРАВИЛЬНОЕ, минимум 2 ошибки)

4. Используй реальные формулы
5. Задача должна быть решаема

Пиши на русском.
"""
            }
        ]

        task = call_llm(messages)

        if task and validate_task(task):
            return task

    return "Не получилось сгенерировать задачу..."


# =========================
# START MESSAGE
# =========================
def start_session(chat_id):
    task = generate_task()

    sessions[chat_id] = {
        "stage": 0,
        "task": task
    }

    return f"""Учитель! Я плохо понял тему.

Я тут решил задачу:

{task}

Я правильно решил?"""


# =========================
# EVALUATE TEACHER
# =========================
def evaluate_teacher(user_text, task):
    messages = [
        {
            "role": "system",
            "content": """
Ты оцениваешь объяснение учителя.

Ответь строго одним словом:
GOOD или BAD

GOOD:
- объясняет по теме
- есть логика
- помогает понять

BAD:
- короткий ответ
- не объясняет
- не по теме
"""
        },
        {
            "role": "user",
            "content": f"""
ЗАДАЧА:
{task}

ОТВЕТ УЧИТЕЛЯ:
{user_text}
"""
        }
    ]

    result = call_llm(messages)
    return "GOOD" in result if result else False


# =========================
# STUDENT RESPONSE
# =========================
def student_reply(chat_id, user_text):
    session = sessions.get(chat_id)

    if not session:
        return start_session(chat_id)

    stage = session["stage"]
    task = session["task"]

    is_good = evaluate_teacher(user_text, task)

    if not is_good:
        return "Я не очень понял... Можете объяснить подробнее?"

    # GOOD explanation → progression
    session["stage"] += 1

    if session["stage"] == 1:
        return "А можете объяснить это на простом примере из жизни?"

    elif session["stage"] == 2:
        return "Кажется, я начинаю понимать... но всё равно путаюсь..."

    elif session["stage"] == 3:
        return "Я почти понял, но не уверен, правильно ли думаю..."

    else:
        return "Ааа, теперь понял! Спасибо! Теперь вроде всё сходится!"


# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text.lower() == "/start":
            reply = start_session(chat_id)
        else:
            reply = student_reply(chat_id, text)

        send_message(chat_id, reply)

    return jsonify({"ok": True})


# =========================
# HEALTH
# =========================
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
