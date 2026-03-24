import os
import json
import random
import logging
import requests
import re
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras

# Настройка логирования
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

TOPICS_BY_CLASS = {
    7: ["механическое движение", "скорость", "плотность", "сила тяжести", "давление"],
    8: ["работа и мощность", "простые механизмы", "энергия", "теплопроводность"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["молекулярно-кинетическая теория", "термодинамика", "электрическое поле", "магнитное поле", "колебания"]
}

user_sessions = {}

def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def clean_task_text(text):
    text = re.sub(r'\s*\([^)]*ошибка[^)]*\)', '', text, flags=re.IGNORECASE)
    return text.strip()

def generate_task_with_mistakes(cls, topic):
    # Примеры ТИПИЧНЫХ ошибок, чтобы ИИ не выдумывал бред
    mistake_examples = """
    Примеры ТИПИЧНЫХ ошибок школьников:
    - Вместо v = s / t пишет v = s * t (путает умножение и деление).
    - Вместо F = m * g пишет F = m + g (путает сложение и умножение).
    - Вместо I = U / R пишет I = U * R.
    - Забывает перевести единицы (км в м, минуты в часы).
    - Перепутаны буквы в формуле (S вместо V и т.д.).
    """

    prompt = (
        f"Ты - ученик {cls} класса. Тема: {topic}.\n"
        f"{mistake_examples}\n"
        "Придумай простую задачу (без лишних данных).\n"
        "Реши её, допустив ОДНУ ТИПИЧНУЮ ошибку из примеров выше.\n\n"
        
        "ТРЕБОВАНИЯ:\n"
        "1. Пиши уверенно.\n"
        "2. НЕ ПИШИ скобки с пояснениями.\n"
        "3. В ответе пиши число И единицу измерения.\n\n"
        
        "ФОРМАТ:\n"
        "УСЛОВИЕ: [текст]\n"
        "МОЁ РЕШЕНИЕ:\n"
        "1) [обозначения]\n"
        "2) [формула]\n"
        "3) [вычисление]\n"
        "ОТВЕТ: [число ед.изм]"
    )
    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=500,
            temperature=0.7
        )
        task = response.choices[0].message.content.strip()
        return clean_task_text(task)
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return None

def simple_check_task(task_text):
    if not task_text or len(task_text) < 50: return False
    if "УСЛОВИЕ" not in task_text or "ОТВЕТ" not in task_text: return False
    if re.search(r'\([^)]*(ошибка|забыл|напишу)[^)]*\)', task_text, re.IGNORECASE): return False
    return True

def generate_smart_fallback(cls, topic):
    v = random.choice([12, 15, 18, 20])
    m = random.choice([2, 3, 5, 8, 10])
    s = random.choice([10, 20, 50])
    
    fallbacks = {
        7: {
            "механическое движение": f"Машина проехала {s*2} км за 2 часа. Скорость?\nМОЁ РЕШЕНИЕ:\n1) v - скорость.\n2) v = t / s (Ошибка: время делю на путь!)\n3) v = 2 / {s*2} = {round(2/(s*2),2)}\nОТВЕТ: {round(2/(s*2),2)} км/ч",
            "скорость": f"Велосипедист едет {s} км со скоростью {v} км/ч. Время?\nМОЁ РЕШЕНИЕ:\n1) t - время.\n2) t = s * v (Ошибка: умножаю!)\n3) t = {s} * {v} = {s*v}\nОТВЕТ: {s*v} ч",
            "плотность": f"Масса {m} кг, объём {m*2} м³. Плотность?\nМОЁ РЕШЕНИЕ:\n1) ρ - плотность.\n2) ρ = m + V (Ошибка: складываю!)\n3) ρ = {m} + {m*2} = {m*3}\nОТВЕТ: {m*3} кг/м³"
        },
        9: {
            "ток": f"Напряжение 12 В, сопротивление 4 Ом. Ток?\nМОЁ РЕШЕНИЕ:\n1) I - ток.\n2) I = U + R (Ошибка: складываю!)\n3) I = 12 + 4 = 16\nОТВЕТ: 16 А",
            "движение": f"Скорость 10 м/с, время 5 с. Путь?\nМОЁ РЕШЕНИЕ:\n1) s - путь.\n2) s = v - t (Ошибка: вычитаю!)\n3) s = 10 - 5 = 5\nОТВЕТ: 5 м"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
        if class_tasks: task = list(class_tasks.values())[0]
        else: task = f"Задача по теме {topic}. Масса {m} кг. F = m + 10 = {m+10} Н."
            
    return clean_task_text(task)

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = generate_task_with_mistakes(cls, topic)
    
    if not task or not simple_check_task(task):
        task = generate_smart_fallback(cls, topic)
        
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
            f"Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task

def check_teacher_quality(message):
    words = message.split()
    if len(words) < 4: return False
    
    bad_phrases = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси", "сомневаюсь"]
    if any(p in message.lower() for p in bad_phrases) and len(words) < 15: return False

    prompt = (
        f"Ученик спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n"
        "Это полезный ответ? (true/false). JSON: {\"is_relevant\": true/false}"
    )
    try:
        resp = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b", max_tokens=50, temperature=0.1
        )
        content = resp.choices[0].message.content
        if '{' in content:
            json_part = content[content.find('{'):content.rfind('}')+1]
            data = json.loads(json_part)
            return data.get("is_relevant", False)
    except Exception: pass
    return True

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    is_relevant = check_teacher_quality(user_message)
    
    if not is_relevant:
        action = "STAY_CONFUSED"
    else:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']
        if good_count == 1: action = "ASK_EXAMPLE"
        elif good_count == 2: action = "PARTIAL_FIX"
        elif good_count == 3: action = "ALMOST_THERE"
        else: action = "SUCCESS"

    task = session.get('task', '')
    topic = session.get('topic', 'физика')
    history = format_history(session.get('messages', []))
    
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель уклонился от ответа.\n"
            "Твоя реакция:\n"
            "1. Удивись, что учитель молчит.\n"
            "2. Спроси прямо: 'Так правильно или нет?'\n"
            "3. Пиши ТОЛЬКО свою фразу. НЕ используй формат 'Учитель: ...'."
        )
    elif action == "ASK_EXAMPLE":
        instr = "Учитель объяснил. Попроси пример из жизни. НЕ исправляй решение."
    elif action == "PARTIAL_FIX":
        instr = "Исправь ОДНУ ошибку, сделай другую. Спроси: 'Так верно?'"
    elif action == "ALMOST_THERE":
        instr = "Реши почти правильно. Спроси: 'Теперь так?'"
    else: 
        instr = "Реши ПРАВИЛЬНО. Поблагодари."

    prompt = (
        f"ТЫ — ученик. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"КОНТЕКСТ:\n{history}\n\n"
        f"УЧИТЕЛЬ: {user_message}\n\n"
        f"ЦЕЛЬ: {instr}\n\n"
        "ВАЖНО: Пиши только текст своего ответа. Не добавляй 'Учитель:', 'Я:' и не цитируй чужие реплики."
    )

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b", max_tokens=500, temperature=0.7
        )
        result = response.choices[0].message.content.strip()
        
        # Защита от сбоев формата
        if ":" in result and ("Учитель" in result or "Я:" in result):
            parts = re.split(r'(Учитель:|Я:|Ученик:)', result)
            result = parts[-1].strip()
            
        return result
    except Exception as e:
        logger.error(f"Gen error: {e}")
        return "Я не понял."

def format_history(messages):
    if not messages: return "Начало"
    lines = []
    for m in messages[-4:]:
        role = "Учитель" if m['role']=='user' else "Ученик"
        lines.append(f"{role}: {m['content'][:80]}")
    return "\n".join(lines)

@app.route('/')
def index(): return "OK"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data or 'message' not in data: return jsonify({"status": "ok"})
        
        msg = data['message']
        if 'text' not in msg: return jsonify({"status": "ok"})
        
        user_msg = msg['text'].strip()
        chat_id = msg['chat']['id']
        
        if user_msg == '/start':
            welcome, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {'class': cls, 'topic': topic, 'task': task, 'messages': [], 'good_explanations': 0}
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})
        
        session = user_sessions.get(chat_id)
        if not session:
            welcome, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {'class': cls, 'topic': topic, 'task': task, 'messages': [], 'good_explanations': 0}
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})
        
        response = get_student_response(user_msg, session)
        
        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response})
        if len(session['messages']) > 10: session['messages'] = session['messages'][-10:]
        
        send_message(chat_id, response)
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e: logger.error(f"Send error: {e}")

if __name__ == '__main__':
    app.run(debug=True, port=5000)
