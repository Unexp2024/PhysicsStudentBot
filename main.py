import os
import requests
from flask import Flask, request, jsonify

# ----------------------------
# CONFIG
# ----------------------------
TOKEN = os.environ.get("TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

app = Flask(__name__)

# ----------------------------
# SYSTEM PROMPT (УСИЛЕННЫЙ)
# ----------------------------
SYSTEM_PROMPT = """
Ты — школьник, который плохо понимает физику.

ФОРМАТ (СТРОГО ОБЯЗАТЕЛЕН):

Учитель! Я плохо понял тему <ТЕМА>.

Я тут решил задачу:

ЗАДАЧА:
<полное условие задачи, минимум 2 числовых параметра, физически корректная>

ЧТО НАЙТИ:
<одна конкретная величина>

РЕШЕНИЕ УЧЕНИКА:
<неправильное решение с минимум 2 РЕАЛИСТИЧНЫМИ ошибками>

Я правильно решил?

ПРАВИЛА:
- Пиши ТОЛЬКО на русском
- Обращайся на "Вы"
- Ты НЕ учитель
- Ты НЕ объясняешь
- Ты ОБЯЗАН ошибаться

КРИТИЧНО:
- ЗАДАЧА должна быть ПОЛНОЙ (никаких "параметры: 10 и 5")
- Должно быть ясно, что искать
- Все необходимые данные должны присутствовать
- НЕ дублируй данные (например сила трения + коэффициент одновременно)

ФИЗИКА:
- Не нарушай законы физики
- Если есть трение → оно уменьшает скорость
- Если движение равномерное → нет ускорения
- Не придумывай несуществующие силы

ОШИБКИ УЧЕНИКА:
Допустимые:
- ошибка в формуле
- ошибка в знаке
- ошибка в расчёте
- путаница единиц

Запрещено:
- бессмысленные формулы
- случайные действия без логики
"""

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
def call_llm(messages, temperature=0.7):
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(CEREBRAS_URL, headers=headers, json={
        "model": "llama3.1-70b",
        "messages": messages,
        "temperature": temperature
    })

    return response.json()["choices"][0]["message"]["content"]

# ----------------------------
# VALIDATION (КЛЮЧЕВОЕ)
# ----------------------------
def validate_task(text):
    validation_prompt = f"""
Проверь задачу по физике.

Ответь ТОЛЬКО:
VALID
или
INVALID: причина

Проверь:
1. Есть ли тема
2. Есть ли полное условие задачи
3. Есть ли что найти
4. Есть ли решение ученика
5. Хватает ли данных
6. Нет ли противоречий
7. Не нарушена ли физика
8. Нет ли лишних/дублирующих данных

ТЕКСТ:
{text}
"""

    result = call_llm([
        {"role": "system", "content": "Ты строгий преподаватель физики."},
        {"role": "user", "content": validation_prompt}
    ], temperature=0)

    return result

# ----------------------------
# GENERATION + RETRY
# ----------------------------
def generate_valid_task():
    for attempt in range(3):
        text = call_llm([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Начни диалог."}
        ])

        validation = validate_task(text)

        if validation.startswith("VALID"):
            return text

        # если плохо — усиливаем запрос
        SYSTEM_RETRY = SYSTEM_PROMPT + f"\n\nПРЕДЫДУЩАЯ ОШИБКА:\n{validation}\nИсправь это."

        text = call_llm([
            {"role": "system", "content": SYSTEM_RETRY},
            {"role": "user", "content": "Сгенерируй заново."}
        ])

        validation = validate_task(text)

        if validation.startswith("VALID"):
            return text

    # fallback (чтобы бот не молчал)
    return "Учитель! Я плохо понял тему скорость. Я тут решил задачу, но запутался... Я правильно решил?"

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
        user_text = data["message"].get("text", "")

        if user_text.lower() == "/start":
            response = generate_valid_task()
        else:
            response = "А можете объяснить это на простом примере из жизни?"

        send_message(chat_id, response)

    return jsonify({"ok": True})

# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
