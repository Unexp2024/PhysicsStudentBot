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
# Остальная часть файла (webhook, send_message и т.д.) — без изменений
# ------------------------------

# ... (весь остальной код из твоего файла: webhook, send_message, run_tests и т.д.)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        run_tests()
    else:
        app.run(debug=True, port=5000)
