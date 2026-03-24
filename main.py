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

# Получение токенов из переменных окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')

if not TELEGRAM_TOKEN or not CEREBRAS_API_KEY:
    logger.error("Отсутствуют необходимые переменные окружения!")
    raise ValueError("TELEGRAM_TOKEN и CEREBRAS_API_KEY должны быть установлены")

# Инициализация Cerebras
cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# Темы по классам
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
    """Удаляет явные метки ошибок, чтобы ученик выглядел уверенным"""
    # Удаляем текст в скобках, начинающийся с "ошибка"
    text = re.sub(r'\s*\([^)]*ошибка[^)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\([^)]*неверно[^)]*\)', '', text, flags=re.IGNORECASE)
    return text.strip()

def generate_task_with_mistakes(cls, topic):
    """
    Генератор задач. Просим ИИ сгенерировать решение, в котором УЧЕНИК УВЕРЕН.
    """
    prompt = f"""Ты - ученик {cls} класса. Тема: "{topic}".
Придумай задачу и реши её.
Ты УВЕРЕН, что решил правильно, но на самом деле в решении 2-3 грубые ошибки (неправильная формула, арифметика или единицы измерения).

ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:
1. Пиши так, будто ты считаешь своё решение верным.
2. НЕ пиши слова "ошибка", "неверно", "я ошибся". Пиши уверенно.
3. Задача должна быть обычной школьной задачей.

ФОРМАТ:
УСЛОВИЕ: [текст задачи]
МОЁ РЕШЕНИЕ:
1) [обозначения]
2) [формула]
3) [вычисление]
ОТВЕТ: [число]

Задача:"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=600,
            temperature=0.7
        )
        task = response.choices[0].message.content.strip()
        # Финальная очистка от меток, если ИИ их вставил
        return clean_task_text(task)
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return None

def simple_check_task(task_text):
    if not task_text or len(task_text) < 50:
        return False, {"reason": "too_short"}
    checks = {
        "has_numbers": any(c.isdigit() for c in task_text),
        "has_structure": "УСЛОВИЕ" in task_text and "ОТВЕТ" in task_text,
    }
    return all(checks.values()), checks

def generate_smart_fallback(cls, topic):
    """Fallback с теми же правилами - без меток ошибок в тексте"""
    v = random.choice([12, 15, 18, 20, 24, 30, 36, 45])
    t = random.choice([0.5, 1, 1.5, 2, 2.5, 3, 4])
    m = random.choice([2, 3, 5, 8, 10, 12, 15, 20])
    h = random.choice([1, 1.5, 2, 2.5, 3, 4, 5, 6])
    F = random.choice([10, 20, 50, 100, 150, 200, 250, 300])
    s = random.choice([5, 10, 20, 50, 100, 150, 200, 300])
    a = random.choice([2, 3, 4, 5, 6, 8, 10])
    n = random.choice([10, 20, 30, 40, 50])

    # Словарь с примерами (здесь написаны "ошибка" для понимания, но clean_task_text их уберет перед отправкой)
    fallbacks = {
        7: {
            "скорость": [
                f"Велосипедист едет со скоростью {v} км/ч. Сколько времени он потратит на путь {s} км?\nМОЁ РЕШЕНИЕ:\n1) t - время, s - путь, v - скорость\n2) t = s * v (ошибка: умножение!)\n3) t = {s} * {v} = {s*v} ч\nОТВЕТ: {s*v} ч",
            ],
            "сила тяжести": [
                f"Кирпич массой {m} кг падает. Сила тяжести? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F - сила, m - масса, g\n2) F = m + g (ошибка: сложение!)\n3) F = {m} + 10 = {m+10} Н\nОТВЕТ: {m+10} Н"
            ]
        },
        10: {
             "движение по окружности": [
                f"Колесо радиусом {h} м. Скорость {v//2} м/с. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение, v - скорость, R - радиус\n2) a = v + R (ошибка: сложение!)\n3) a = {v//2} + {h} = {v//2+h} м/с²\nОТВЕТ: {v//2+h} м/с²",
            ]
        }
    }
    
    # Достаем задачу (логика вашего старого кода)
    class_tasks = fallbacks.get(cls, {})
    tasks = class_tasks.get(topic, [])
    if not tasks:
        # Если темы нет, берем любую из класса
        for t in class_tasks.values():
            tasks.extend(t)
    
    if tasks:
        return clean_task_text(random.choice(tasks))
    
    # Если совсем пусто
    return f"Задача по теме {topic}. Масса {m} кг. Найти силу. F = m + 10 = {m+10} Н."

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = None
    raw_task = generate_task_with_mistakes(cls, topic)
    
    if raw_task:
        is_ok, _ = simple_check_task(raw_task)
        if is_ok:
            task = raw_task
    
    if not task:
        task = generate_smart_fallback(cls, topic)
        
    return f"""Учитель! Что-то я плохо понял тему "{topic}". Давайте я попробую решить задачу по ней:

{task}

Я правильно решил?""", cls, topic, task

def check_teacher_quality(message):
    """
    Строгий фильтр качества.
    Возвращает JSON с оценкой.
    """
    prompt = f"""Оцени качество ответа учителя.
Сообщение учителя: "{message}"

КРИТЕРИИ ПЛОХОГО ОТВЕТА:
- Очень короткий (меньше 5 слов)
- Нет формул или конкретных объяснений
- Фразы "подумай", "ну не знаю", "перечитай"
- Общая отмазка без конкретики

Ответь ТОЛЬКО JSON:
{{
    "is_relevant": true/false,
    "reason": "краткая причина"
}}"""

    try:
        resp = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=100,
            temperature=0.1
        )
        content = resp.choices[0].message.content
        # Простой парсинг
        if '{' in content:
            json_part = content[content.find('{'):content.rfind('}')+1]
            data = json.loads(json_part)
            return data.get("is_relevant", False)
    except Exception as e:
        logger.error(f"Check quality error: {e}")
    
    # Если ошибка, считаем中性, но лучше перестраховаться
    if len(message.split()) < 4:
        return False
    return True

def get_student_response(user_message, session):
    """Генерация ответа с учетом 'Системного промта'"""
    
    # Считаем количество ХОРОШИХ объяснений
    good_count = session.get('good_explanations', 0)
    
    # Оцениваем текущее сообщение учителя
    is_relevant = check_teacher_quality(user_message)
    
    # Логика смены состояний
    if not is_relevant:
        # Учитель ответил плохо
        action = "STAY_CONFUSED"
        # Не увеличиваем счетчик good_count
    else:
        # Учитель ответил хорошо
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

    # Формируем промт на основе действия
    task = session.get('task', '')
    topic = session.get('topic', 'физика')
    
    instructions = {
        "STAY_CONFUSED": """
Учитель не объяснил толком. Твоя реакция:
- Скажи, что не понял его объяснение.
- Спроси конкретно: "А почему именно так?" или "Где именно у меня ошибка?"
- НЕ исправляй своё решение.
- Будь настойчивым, но вежливым.""",
        
        "ASK_EXAMPLE": """
Учитель дал первое хорошее объяснение. Твоя реакция:
- Скажи: "О, кажется, начал понимать..."
- НО ТЫ ОБЯЗАН задать вопрос: "Можете, пожалуйста, объяснить это на простом примере из жизни?"
- НЕ исправляй решение прямо сейчас.""",
        
        "PARTIAL_FIX": """
Учитель объяснил второй раз (хорошо). Твоя реакция:
- Скажи: "А, теперь понятнее!"
- ИСПРАВЬ ОДНУ ошибку из своего решения.
- НО СДЕЛАЙ НОВУЮ ошибку (например, в вычислениях или единицах измерения).
- Спроси: "А так правильно?"
- Будь уверен в себе.""",
        
        "ALMOST_THERE": """
Учитель объяснил третий раз. Твоя реакция:
- Скажи: "Кажется, я догадался!"
- Реши почти правильно, но оставь маленькую неточность (например, забудь единицы измерения или округли неправильно).
- Спроси: "Я молодец?"",
        
        "SUCCESS": """
Учитель помог тебе разобраться (4-й раз). Твоя реакция:
- Скажи: "Ура! Теперь точно понял!"
- Напиши ПРАВИЛЬНОЕ решение.
- Поблагодари учителя."""
    }

    instr = instructions.get(action, instructions["STAY_CONFUSED"])
    
    prompt = f"""Ты - ученик. Тема: "{topic}".
Твоя задача, которую ты решал:
{task}

ИСТОРИЯ (для контекста):
{format_history(session.get('messages', []))}

ПОСЛЕДНЕЕ СООБЩЕНИЕ УЧИТЕЛЯ:
"{user_message}"

ИНСТРУКЦИЯ ДЛЯ ТВОЕГО ОТВЕТА:
{instr}

ВАЖНО:
- Пиши ТОЛЬКО свой ответ. Не пиши "Учитель:" и историю.
- Не используй обращение "ты", используйте "вы".
- Будь эмоциональным школьником.
"""

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
    return "\n".join([f"{'Учитель' if m['role']=='user' else 'Ученик'}: {m['content'][:80]}" for m in messages[-4:]])

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
        
        # Генерация ответа
        response = get_student_response(user_msg, session)
        
        # Сохранение истории
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
