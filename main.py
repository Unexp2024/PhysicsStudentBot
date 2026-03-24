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
    text = re.sub(r'\s*\([^)]*ошибка[^)]*\)', '', text, flags=re.IGNORECASE)
    return text.strip()

def generate_task_with_mistakes(cls, topic):
    # Добавили требования здравого смысла
    prompt = (
        f"Ты - ученик {cls} класса. Тема: {topic}.\n"
        "Создай задачу и РЕШИ ЕЁ НЕПРАВИЛЬНО.\n"
        "КРИТИЧЕСКИ ВАЖНО:\n"
        "1. Твое решение ДОЛЖНО содержать ошибку! НЕ решай правильно!\n"
        "2. Задача должна быть РЕАЛИСТИЧНОЙ. Соблюдай здравый смысл (например, длина наклонной плоскости всегда больше её высоты).\n"
        "3. В ответе ВСЕГДА пиши число И единицу измерения.\n\n"
        
        "ПРИМЕРЫ ОШИБОК:\n"
        "- Сложение вместо умножения (F = m + g).\n"
        "- Перепутаны переменные (t = s * v вместо t = s / v).\n"
        "- Путаница в единицах.\n\n"
        
        "ФОРМАТ:\n"
        "УСЛОВИЕ: [текст задачи]\n"
        "МОЁ РЕШЕНИЕ:\n"
        "1) [обозначения]\n"
        "2) [формула]\n"
        "3) [вычисление]\n"
        "ОТВЕТ: [число и единица измерения]\n\n"
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
    v = random.choice([12, 15, 18, 20, 24, 30])
    m = random.choice([2, 3, 5, 8, 10])
    h = random.choice([1, 1.5, 2, 2.5, 3])
    s = random.choice([5, 10, 20, 50, 100])
    
    fallbacks = {
        7: {
            "скорость": f"Велосипедист едет со скоростью {v} км/ч. Сколько времени он потратит на путь {s} км?\nМОЁ РЕШЕНИЕ:\n1) t - время, s - путь, v - скорость\n2) t = s * v\n3) t = {s} * {v} = {s*v}\nОТВЕТ: {s*v} ч",
            "плотность": f"Найдите плотность вещества, если масса {m} кг, а объём {m*2} м³.\nМОЁ РЕШЕНИЕ:\n1) m - масса, V - объём\n2) ρ = m + V\n3) ρ = {m} + {m*2} = {m*3}\nОТВЕТ: {m*3} кг/м³"
        },
        8: {
            "простые механизмы": f"С помощью рычага рабочий поднимает груз массой {m*10} кг. Плечо силы рабочего 2 м, а плечо силы груза 0.5 м. Какую силу прикладывает рабочий?\nМОЁ РЕШЕНИЕ:\n1) F1 - сила рабочего, F2 - сила тяжести груза, l1 и l2 - плечи.\n2) F1 = F2 * l2 / l1 (Ошибка: перепутал плечи местами в формуле!)\n3) F2 = {m*10} * 10 = {m*100} Н. F1 = {m*100} * 2 / 0.5 = {m*400} Н.\nОТВЕТ: {m*400} Н."
        },
        9: {
            "ток": f"Напряжение 12 В, сопротивление 4 Ом. Найдите ток.\nМОЁ РЕШЕНИЕ:\n1) I - ток, U - напряжение, R - сопротивление\n2) I = U + R\n3) I = 12 + 4 = 16\nОТВЕТ: 16 А"
        },
        10: {
             "движение по окружности": f"Колесо радиусом {h} м. Скорость {v//2} м/с. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение, v - скорость, R - радиус\n2) a = v + R\n3) a = {v//2} + {h} = {v//2+h}\nОТВЕТ: {v//2+h} м/с²"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
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
    words = message.split()
    if len(words) < 4:
        return False
    
    # Список "пустых" ответов, которые не помогают
    bad_phrases = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси"]
    if any(p in message.lower() for p in bad_phrases) and len(words) < 10:
        return False

    prompt = (
        f"Ученик решил задачу и спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n"
        "Является ли этот ответ ПОЛЕЗНЫМ объяснением?\n"
        "Если учитель уклонился от ответа или не указал на ошибку - это false.\n"
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
    
    # Проверяем, является ли сообщение "отпиской"
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
    
    # Инструкции
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель ответил нечетко, ушел от ответа или сказал 'не знаю'.\n"
            "Твоя реакция:\n"
            "1. НЕ выдумывай, что учитель сказал 'неправильно'. Он просто ничего не сказал.\n"
            "2. Вырази недоумение или разочарование.\n"
            "3. Спроси прямо: 'Так это правильный ответ или нет?'\n"
            "4. НЕ повторяй свои предыдущие сообщения полностью.\n"
            "5. Используй разные формулировки."
        )
    elif action == "ASK_EXAMPLE":
        instr = (
            "Учитель дал хорошее объяснение.\n"
            "Твоя реакция:\n"
            "- Скажи: 'О, теперь понятнее...'\n"
            "- ОБЯЗАТЕЛЬНО попроси: 'А можно пример из жизни?'\n"
            "- НЕ исправляй решение."
        )
    elif action == "PARTIAL_FIX":
        instr = (
            "Учитель объяснил второй раз.\n"
            "Твоя реакция:\n"
            "- Скажи: 'А, кажется, я понял!'\n"
            "- ИСПРАВЬ ОДНУ ошибку.\n"
            "- НО СДЕЛАЙ НОВУЮ мелкую ошибку.\n"
            "- Спроси: 'Вот так правильно?'"
        )
    elif action == "ALMOST_THERE":
        instr = (
            "Учитель помог еще раз.\n"
            "Твоя реакция:\n"
            "- Скажи: 'Кажется, дошло!'\n"
            "- Реши почти правильно.\n"
            "- Спроси: 'Теперь верно?'"
        )
    else: # SUCCESS
        instr = (
            "Ты наконец понял.\n"
            "Твоя реакция:\n"
            "- Скажи: 'Ура! Теперь точно понял!'\n"
            "- Напиши ПРАВИЛЬНОЕ решение.\n"
            "- Поблагодари учителя."
        )

    # Добавляем историю в промт, чтобы избежать повторов
    prompt = (
        f"Ты - ученик. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"ИСТОРИЯ ДИАЛОГА:\n{history}\n\n"
        f"ПОСЛЕДНЕЕ СООБЩЕНИЕ УЧИТЕЛЯ:\n{user_message}\n\n"
        f"ИНСТРУКЦИЯ ДЛЯ ОТВЕТА:\n{instr}\n\n"
        "ВАЖНО: Не повторяй текст своих прошлых сообщений из истории! Напиши что-то новое."
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
    for m in messages[-6:]: # Увеличил окно истории
        role = "Учитель" if m['role']=='user' else "Ученик"
        lines.append(f"{role}: {m['content'][:100]}")
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
        if len(session['messages']) > 10: session['messages'] = session['messages'][-10:]
        
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
