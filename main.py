import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

sessions = {}

# =========================
# TELEGRAM
# =========================
def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

# =========================
# LLM CALL
# =========================
def call_llm(messages, temperature=0.7):
    try:
        response = requests.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama3.1-8b",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 700
            },
            timeout=25
        )

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        print("LLM ERROR:", e)
        return None


# =========================
# VALIDATE STRUCTURE
# =========================
def validate_structure(text):
    if not text:
        return False

    required = [
        "Я плохо понял тему",
        "ЗАДАЧА:",
        "ЧТО НАЙТИ:",
        "РЕШЕНИЕ УЧЕНИКА:",
        "Я правильно решил?"
    ]

    for r in required:
        if r not in text:
            return False

    return True


# =========================
# LLM TASK CHECKER
# =========================
def validate_physics(task):
    messages = [
        {
            "role": "system",
            "content": """
Проверь задачу по физике.

Ответь только:
VALID или INVALID

Критерии:
- задача физически корректна
- все необходимые параметры заданы
- задача имеет однозначное решение
- нет бессмысленных формулировок
"""
        },
        {
            "role": "user",
            "content": task
        }
    ]

    result = call_llm(messages, temperature=0)

    if not result:
        return False

    return "VALID" in result


# =========================
# GENERATE STUDENT MESSAGE
# =========================
def generate_student_problem():
    for _ in range(6):

        messages = [
            {
                "role": "system",
                "content": """
Ты школьник 7-10 класса, который плохо понимает физику.

Сгенерируй сообщение учителю.

СТРОГО В ФОРМАТЕ:

Учитель! Я плохо понял тему <укажи тему>.

Я тут решил задачу:

ЗАДАЧА:
(полное условие задачи, как в учебнике, все параметры заданы)

ЧТО НАЙТИ:
(одна величина)

РЕШЕНИЕ УЧЕНИКА:
(неправильное решение с типичными школьными ошибками:
неправильная формула, ошибка в вычислениях или путаница единиц)

Я правильно решил?

ТРЕБОВАНИЯ:
- задача должна быть физически корректной
- все данные должны быть указаны
- задача должна иметь решение
- НЕ придумывай странные рассуждения
- стиль школьника
"""
            }
        ]

        text = call_llm(messages)

        if not validate_structure(text):
            continue

        if not validate_physics(text):
            continue

        return text

    # fallback
    return """Учитель! Я плохо понял тему импульс.

Я тут решил задачу:

ЗАДАЧА:
Тело массой 2 кг движется со скоростью 3 м/с.

ЧТО НАЙТИ:
Импульс тела.

РЕШЕНИЕ УЧЕНИКА:
Я подумал, что импульс это масса плюс скорость.
Поэтому 2 + 3 = 5.

Я правильно решил?
"""


# =========================
# START SESSION
# =========================
def start_session(chat_id):
    msg = generate_student_problem()

    sessions[chat_id] = {
        "stage": 0,
        "task": msg
    }

    return msg


# =========================
# EVALUATE TEACHER
# =========================
def evaluate_teacher(user_text, task):
    messages = [
        {
            "role": "system",
            "content": """
Ты оцениваешь объяснение учителя.

Ответь только:
GOOD
или
BAD

GOOD если:
- объяснение по теме
- помогает понять
- есть логика

BAD если:
- коротко
- не объясняет
- не по теме
"""
        },
        {
            "role": "user",
            "content": f"""
Задача ученика:
{task}

Ответ учителя:
{user_text}
"""
        }
    ]

    result = call_llm(messages, temperature=0)

    if not result:
        return False

    return "GOOD" in result


# =========================
# STUDENT PROGRESSION
# =========================
def student_reply(chat_id, user_text):
    session = sessions.get(chat_id)

    if not session:
        return start_session(chat_id)

    stage = session["stage"]
    task = session["task"]

    good = evaluate_teacher(user_text, task)

    if not good:
        return "Я всё равно не очень понял... Можете объяснить подробнее?"

    stage += 1
    session["stage"] = stage

    if stage == 1:
        return "А можно объяснить это ещё проще?"

    if stage == 2:
        return "Кажется, я начинаю понимать..."

    if stage == 3:
        return "Ааа, теперь понял! Спасибо!"

    return "Спасибо! Теперь я понял тему."


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
