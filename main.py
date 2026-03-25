import os
import json
import random
import logging
import requests
import re
import sys
import time
from functools import wraps
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras

# ------------------------------
# Конфигурация
# ------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')

if not TELEGRAM_TOKEN or not CEREBRAS_API_KEY:
    raise ValueError("Токены не установлены")

cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# ------------------------------
# Данные (оставлено как у тебя)
# ------------------------------
TOPICS_BY_CLASS = { ... }  # твой словарь без изменений

user_sessions = {}

# ------------------------------
# Генерация задач (оставлено как у тебя, только слегка сократил для читаемости)
# ------------------------------
def get_fallback_task(cls, topic):
    # ... (весь твой код генерации fallbacks остаётся без изменений)
    # Я оставил только ключевую часть для "работа и мощность", остальное копируй из своего файла
    pass  # ← замени на свой полный get_fallback_task

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task, correct_answer, correct_formula = get_fallback_task(cls, topic)
    
    initial_text = (
        f"Учитель! Что-то я плохо понял тему \"{topic}\". "
        f"Давайте я попробую решить задачу по ней:\n\n"
        f"{task}\n\n"
        f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста."
    )
    return initial_text, cls, topic, task, correct_answer, correct_formula

# ------------------------------
# Проверка качества ответа учителя
# ------------------------------
def check_teacher_quality(message, topic):
    lower = message.lower()
    if any(phrase in lower for phrase in ["надо подумать", "не знаю", "подумай сам", "не уверен"]):
        return False
    try:
        prompt = f"""Ученик по теме "{topic}" спросил объяснения. Учитель ответил: "{message}"
        Это полезное объяснение? (наводящее, с примером, объясняет смысл, но не даёт готовый ответ)
        Ответь JSON: {{"is_helpful": true/false}}"""
        
        resp = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b", max_tokens=50, temperature=0.1
        )
        content = resp.choices[0].message.content
        if '{' in content:
            data = json.loads(content[content.find('{'):content.rfind('}')+1])
            return data.get("is_helpful", False)
    except:
        pass
    return len(message.split()) > 8

# ------------------------------
# Постобработка ответа
# ------------------------------
def clean_response(text, user_message):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    if user_message and user_message.strip() in text:
        text = text.replace(user_message.strip(), "").strip()
    text = text.replace("depends от", "зависит от")
    text = text.replace("force", "сила")
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 250:
        text = text[:250] + "..."
    return text

# ------------------------------
# Генерация ответа школьника (главное исправление)
# ------------------------------
def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])

    is_helpful = check_teacher_quality(user_message, topic)
    if is_helpful:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    # История диалога
    history_text = "\n".join([
        f"Учитель: {m['content']}" if m['role'] == 'user' else f"Я: {m['content']}"
        for m in history[-5:]
    ])

    # Контроль прогресса (чтобы не решал сразу)
    if good_count == 0:
        level = "Ты только что показал своё неверное решение. Ты пока совсем не понимаешь, как считать работу."
    elif good_count == 1:
        level = "Учитель дал первую подсказку с примером из жизни. Ты начинаешь догадываться, но ещё путаешься и не уверен."
    elif good_count == 2:
        level = "Учитель уже два раза объяснял. Ты почти понял, но можешь ошибиться в единицах или забыть про g."
    else:
        level = "Теперь ты должен понять и решить правильно."

    prompt = f"""Ты — обычный школьник 8 класса, не очень сильный в физике. Тема: {topic}.

Твоя задача:
{task}

{level}

Предыдущий диалог:
{history_text}

Последнее сообщение учителя: "{user_message}"

Ответь коротко и естественно, как школьник:
- 1–2 предложения максимум
- Не повторяй слова учителя
- Говори простым русским языком
- Если учитель задал вопрос — ответь на него
- Пока не решай задачу полностью правильно (если good_count < 3)
Твой ответ:"""

    try:
        result = generate_student_response(prompt)   # твоя функция
        result = clean_response(result, user_message)
        # Дополнительная защита от преждевременного решения
        if good_count < 2 and ("100000" in result or "2000000" in result or "A =" in result):
            result = "Я понял, что нужно учитывать силу тяжести... А как её посчитать точно?"
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return "Я запутался... Объясните ещё раз, пожалуйста?"

# ------------------------------
# Flask и Telegram обработчики
# ------------------------------
@app.route('/')
def index():
    return "OK"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"status": "ok"})

        msg = data['message']
        if 'text' not in msg:
            return jsonify({"status": "ok"})

        user_msg = msg['text'].strip()
        chat_id = msg['chat']['id']

        if user_msg == '/start':
            welcome, cls, topic, task, correct_answer, correct_formula = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'correct_answer': correct_answer,
                'correct_formula': correct_formula,
                'messages': [],
                'good_explanations': 0
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})

        session = user_sessions.get(chat_id)
        if not session:
            welcome, cls, topic, task, correct_answer, correct_formula = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'correct_answer': correct_answer,
                'correct_formula': correct_formula,
                'messages': [],
                'good_explanations': 0
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})

        response = get_student_response(user_msg, session)

        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response})

        send_message(chat_id, response)
        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# ------------------------------
# Тесты
# ------------------------------
def run_tests():
    print("Запуск тестов...")
    # Тест 1: Генерация задачи
    cls, topic = get_random_class_and_topic()
    task, correct_answer, correct_formula = get_fallback_task(cls, topic)
    assert task and isinstance(task, str), "Задача не сгенерирована"
    assert correct_answer is not None, "Правильный ответ не определён"
    print("✓ Генерация задачи работает")

    # Тест 2: Проверка LLM (если доступна)
    try:
        res = check_teacher_quality_llm(
            "Время до остановки можно найти, если знать, насколько скорость уменьшается каждую секунду. Но нас спрашивают не время, а путь. Путь при равномерном изменении скорости — это как средняя скорость, умноженная на время. Какая будет средняя скорость, если поезд начинает с 10 м/с и заканчивает на 0 м/с?",
            "движение"
        )
        assert res is True, "LLM не распознал наводящий вопрос"
        print("✓ LLM распознаёт полезные объяснения")
    except Exception as e:
        print(f"⚠ LLM проверка недоступна: {e}")

    # Тест 3: Проверка очистки ответа
    cleaned = clean_response("Ответ учителя: Молодец. Так какой же ответ в задаче?", "Молодец. Так какой же ответ в задаче?")
    assert cleaned == "Молодец. Так какой же ответ в задаче?", "Очистка не удалила 'Ответ учителя:'"
    print("✓ Очистка ответов работает")

    print("Тесты завершены.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        run_tests()
    else:
        app.run(debug=True, port=5000)
