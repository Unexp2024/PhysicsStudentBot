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

# Инициализация Flask
app = Flask(__name__)

# Получение токенов
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')

if not TELEGRAM_TOKEN or not CEREBRAS_API_KEY:
    logger.error("Отсутствуют переменные окружения!")
    raise ValueError("Токены не установлены")

# Инициализация Cerebras
cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# Темы
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
    """Удаляет метки ошибок, чтобы ученик выглядел уверенным"""
    text = re.sub(r'\s*\([^)]*ошибка[^)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\([^)]*неверно[^)]*\)', '', text, flags=re.IGNORECASE)
    return text.strip()

def generate_task_with_mistakes(cls, topic):
    prompt = (
        f"Ты - ученик {cls} класса. Тема: {topic}.\n"
        "Придумай задачу и реши её.\n"
        "Ты УВЕРЕН, что решил правильно, но на самом деле в решении 2-3 грубые ошибки.\n\n"
        "ФОРМАТ:\n"
        "УСЛОВИЕ: [текст задачи]\n"
        "МОЁ РЕШЕНИЕ:\n"
        "1) [обозначения]\n"
        "2) [формула]\n"
        "3) [вычисление]\n"
        "ОТВЕТ: [число]\n\n"
        "Задача:"
    )
    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=600,
            temperature=0.7
        )
        task = response.choices[0].message.content.strip()
        return clean_task_text(task)
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return None

def simple_check_task(task_text):
    if not task_text or len(task_text) < 50:
        return False
    return "УСЛОВИЕ" in task_text and "ОТВЕТ" in task_text

def generate_smart_fallback(cls, topic):
    v = random.choice([12, 15, 18, 20, 24, 30, 36, 45])
    m = random.choice([2, 3, 5, 8, 10, 12])
    h = random.choice([1, 1.5, 2, 2.5, 3])
    s = random.choice([5, 10, 20, 50, 100])
    
    fallbacks = {
        7: {
            "скорость": f"Велосипедист едет со скоростью {v} км/ч. Сколько времени он потратит на путь {s} км?\nМОЁ РЕШЕНИЕ:\n1) t - время, s - путь, v - скорость\n2) t = s * v\n3) t = {s} * {v} = {s*v} ч\nОТВЕТ: {s*v} ч",
            "сила тяжести": f"Кирпич массой {m} кг падает. Сила тяжести? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F - сила, m - масса\n2) F = m + 10\n3) F = {m} + 10 = {m+10} Н\nОТВЕТ: {m+10} Н"
        },
        10: {
             "движение по окружности": f"Колесо радиусом {h} м. Скорость {v//2} м/с. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение, v - скорость, R - радиус\n2) a = v + R\n3) a = {v//2} + {h} = {v//2+h} м/с²\nОТВЕТ: {v//2+h} м/с²"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
        # Если темы нет, берем первую попавшуюся из класса
        if class_tasks:
            task = list(class_tasks.values())[0]
        else:
            task = f"Задача по теме {topic}. Масса {m} кг. Найти силу. F = m + 10 = {m+10} Н."
            
    return clean_task_text(task)

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = generate_task_with_mistakes(cls, topic)
    
    if not task or not simple_check_task(task):
        task = generate_smart_fallback(cls, topic)
        
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
            f"Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task

def check_teacher_quality(message):
    # Простой эвристический фильтр + LLM проверка
    words = message.split()
    if len(words) < 4:
        return False
    
    bad_phrases = ["не знаю", "подумай", "сам", "перечитай"]
    if any(p in message.lower() for p in bad_phrases):
        return False

    # LLM проверка (быстрая)
    prompt = (
        f"Оцени качество ответа учителя: \"{message}\"\n"
        "Это хорошее объяснение? (true/false). "
        "Ответь только JSON: {\"is_relevant\": true/false}"
    )
    try:
        resp = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=50,
            temperature=0.1
        )
        content = resp.choices[0].message.content
        if '{' in content:
            json_part = content[content.find('{'):content.rfind('}')+1]
            data = json.loads(json_part)
            return data.get("is_relevant", False)
    except Exception:
        pass
    
    return True

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    is_relevant = check_teacher_quality(user_message)
    
    if not is_relevant:
        action = "STAY_CONFUSED"
    else:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']
        
        if good_count == 1:
            action = "ASK_EXAMPLE"
        elif good_count == 2:
            action = "PARTIAL_FIX"
        elif good_count == 3:
            action = "ALMOST_THERE"
        else:
            action = "SUCCESS"

    task = session.get('task', '')
    topic = session.get('topic', 'физика')
    history = format_history(session.get('messages', []))
    
    # Определяем инструкцию в зависимости от действия
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель не объяснил толком. Твоя реакция:\n"
            "- Скажи, что не понял.\n"
            "- Спроси конкретно: 'А почему именно так?'\n"
            "- НЕ исправляй своё решение."
        )
    elif action == "ASK_EXAMPLE":
        instr = (
            "Учитель дал первое хорошее объяснение. Твоя реакция:\n"
            "- Скажи: 'О, кажется, начал понимать...'\n"
            "- ОБЯЗАТЕЛЬНО спроси: 'Можете, пожалуйста, объяснить это на простом примере из жизни?'\n"
            "- НЕ исправляй решение."
        )
    elif action == "PARTIAL_FIX":
        instr = (
            "Учитель объяснил второй раз. Твоя реакция:\n"
            "- Скажи: 'А, теперь понятнее!'\n"
            "- ИСПРАВЬ ОДНУ ошибку.\n"
            "- НО СДЕЛАЙ НОВУЮ ошибку (например, в вычислениях).\n"
            "- Спроси: 'А так правильно?'"
        )
    elif action == "ALMOST_THERE":
        instr = (
            "Учитель объяснил третий раз. Твоя реакция:\n"
            "- Скажи: 'Кажется, я догадался!'\n"
            "- Реши почти правильно, но оставь маленькую неточность.\n"
            "- Спроси: 'Я молодец?'"
        )
    else: # SUCCESS
        instr = (
            "Учитель помог разобраться. Твоя реакция:\n"
            "- Скажи: 'Ура! Теперь точно понял!'\n"
            "- Напиши ПРАВИЛЬНОЕ решение.\n"
            "- Поблагодари учителя."
        )

    # Собираем промт безопасным способом (без сложных кавычек)
    prompt = (
        f"Ты - ученик. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"ИСТОРИЯ:\n{history}\n\n"
        f"ПОСЛЕДНЕЕ СООБЩЕНИЕ УЧИТЕЛЯ:\n{user_message}\n\n"
        f"ИНСТРУКЦИЯ:\n{instr}\n\n"
        "ВАЖНО: Пиши ТОЛЬКО свой ответ. Не пиши 'Учитель:'. Будь эмоциональным школьником."
    )

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Gen error: {e}")
        return "Я не совсем понял..."

def format_history(messages):
    if not messages: return "Начало"
    lines = []
    for m in messages[-4:]:
        role = "Учитель" if m['role']=='user' else "Ученик"
        lines.append(f"{role}: {m['content'][:80]}")
    return "\n".join(lines)

@app.route('/')
def index():
    return "OK"

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
            user_sessions[chat_id] = {
                'class': cls, 'topic': topic, 'task': task,
                'messages': [], 'good_explanations': 0
            }
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
        if len(session['messages']) > 8: session['messages'] = session['messages'][-8:]
        
        send_message(chat_id, response)
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Send error: {e}")

if __name__ == '__main__':
    app.run(debug=True, port=5000)
