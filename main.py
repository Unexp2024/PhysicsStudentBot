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

# Словарь базовых формул, чтобы ИИ не выдумывал "мосты с цепями"
FORMULAS_HINTS = {
    "скорость": "v = s / t",
    "плотность": "ρ = m / V",
    "сила тяжести": "F = m * g",
    "давление": "p = F / S",
    "работа и мощность": "A = F * s",
    "энергия": "E = m * g * h",
    "ток": "I = U / R",
    "законы Ньютона": "F = m * a",
    "импульс": "p = m * v",
    "архимедова сила": "F = ρ * g * V",
    "движение по окружности": "a = v² / R",
    "колебания": "T = t / N",
    "термодинамика": "U = A + Q"
}

def generate_task_with_mistakes(cls, topic):
    formula = FORMULAS_HINTS.get(topic, "стандартная формула")
    
    prompt = (
        f"Ты - ученик {cls} класса. Тема: {topic}.\n"
        f"Базовая формула темы: {formula}.\n\n"
        
        "ЗАДАЧА:\n"
        "1. Придумай ПРОСТОЕ условие (масса, скорость, время и т.д.).\n"
        "2. Реши задачу ИСПОЛЬЗУЯ ОШИБОЧНУЮ ФОРМУЛУ (поменяй знак: + вместо *, / вместо * и т.д.).\n\n"
        
        "КРИТИЧЕСКИ ВАЖНО:\n"
        "- Пиши решение так, будто ты УВЕРЕН, что оно верное.\n"
        "- НЕ ПИШИ комментарии в скобках. Никаких '(ошибка: забыл...)' или '(но я напишу...)'.\n"
        "- Только чистые вычисления.\n\n"
        
        "ФОРМАТ:\n"
        "УСЛОВИЕ: [текст]\n"
        "МОЁ РЕШЕНИЕ:\n"
        "1) [обозначения]\n"
        "2) [формула с ошибкой]\n"
        "3) [вычисление]\n"
        "ОТВЕТ: [число и единица измерения]"
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
    if not task_text or len(task_text) < 50:
        return False
    if "УСЛОВИЕ" not in task_text or "ОТВЕТ" not in task_text:
        return False
    
    # Проверка на "мета-комментарии" (признак бреда)
    if re.search(r'\([^)]*(ошибка|забыл|напишу|имел в виду)[^)]*\)', task_text, re.IGNORECASE):
        logger.warning("Задача забракована: содержит мета-комментарии")
        return False
        
    return True

def generate_smart_fallback(cls, topic):
    v = random.choice([12, 15, 18, 20, 24, 30])
    m = random.choice([2, 3, 5, 8, 10])
    h = random.choice([1, 1.5, 2, 2.5, 3])
    s = random.choice([5, 10, 20, 50, 100])
    F = random.choice([10, 20, 50, 100])
    
    fallbacks = {
        7: {
            "механическое движение": f"Машина проехала {s*2} км за {s//10} часов. Найдите скорость.\nМОЁ РЕШЕНИЕ:\n1) v - скорость, s - путь, t - время.\n2) v = t / s\n3) v = {s//10} / {s*2} = {round((s//10)/(s*2), 2)}\nОТВЕТ: {round((s//10)/(s*2), 2)} км/ч",
            "скорость": f"Велосипедист едет {s} км со скоростью {v} км/ч. Найдите время.\nМОЁ РЕШЕНИЕ:\n1) t - время.\n2) t = s * v\n3) t = {s} * {v} = {s*v}\nОТВЕТ: {s*v} ч",
            "плотность": f"Масса тела {m} кг, объём {m*2} м³. Найдите плотность.\nМОЁ РЕШЕНИЕ:\n1) ρ - плотность.\n2) ρ = m + V\n3) ρ = {m} + {m*2} = {m*3}\nОТВЕТ: {m*3} кг/м³",
            "сила тяжести": f"Масса тела {m} кг. Найти силу тяжести (g=10).\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = m + 10\n3) F = {m} + 10 = {m+10}\nОТВЕТ: {m+10} Н",
            "давление": f"Сила {F} Н давит на площадь {m} м². Найти давление.\nМОЁ РЕШЕНИЕ:\n1) p - давление.\n2) p = F * S\n3) p = {F} * {m} = {F*m}\nОТВЕТ: {F*m} Па"
        },
        8: {
            "работа и мощность": f"Ящик передвинули на {s} м с силой {F} Н. Найти работу.\nМОЁ РЕШЕНИЕ:\n1) A - работа.\n2) A = F - s\n3) A = {F} - {s} = {abs(F-s)}\nОТВЕТ: {abs(F-s)} Дж",
            "энергия": f"Тело массой {m} кг подняли на {h} м. Энергия? (g=10)\nМОЁ РЕШЕНИЕ:\n1) E - энергия.\n2) E = m / h\n3) E = {m} / {h} = {round(m/h,1)}\nОТВЕТ: {round(m/h,1)} Дж"
        },
        9: {
            "ток": f"Напряжение 12 В, сопротивление 4 Ом. Ток?\nМОЁ РЕШЕНИЕ:\n1) I - ток.\n2) I = U + R\n3) I = 12 + 4 = 16\nОТВЕТ: 16 А",
            "законы Ньютона": f"Сила {F} Н, масса {m} кг. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = F + m\n3) a = {F} + {m} = {F+m}\nОТВЕТ: {F+m} м/с²",
            "импульс": f"Масса {m} кг, скорость {v} м/с. Импульс?\nМОЁ РЕШЕНИЕ:\n1) p - импульс.\n2) p = m + v\n3) p = {m} + {v} = {m+v}\nОТВЕТ: {m+v} кг*м/с",
            "колебания": f"Маятник сделал 30 колебаний за 60 секунд. Период?\nМОЁ РЕШЕНИЕ:\n1) T - период.\n2) T = t * N\n3) T = 60 * 30 = 1800\nОТВЕТ: 1800 с"
        },
        10: {
             "движение по окружности": f"Радиус {h} м, скорость {v//2} м/с. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = v + R\n3) a = {v//2} + {h} = {v//2+h}\nОТВЕТ: {v//2+h} м/с²"
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
    
    bad_phrases = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси"]
    if any(p in message.lower() for p in bad_phrases) and len(words) < 10:
        return False

    prompt = (
        f"Ученик решил задачу и спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n"
        "Является ли этот ответ ПОЛЕЗНЫМ объяснением?\n"
        "Если учитель уклонился или не указал на ошибку - это false.\n"
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
    
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель ответил нечетко ('нет', 'подумай', 'не знаю').\n"
            "Твоя реакция:\n"
            "1. Удивись: 'Почему нет? Я же всё подставил в формулу!'\n"
            "2. Спроси: 'А где именно ошибка? В формуле или в счете?'\n"
            "3. Живи только в текущем моменте."
        )
    elif action == "ASK_EXAMPLE":
        instr = (
            "Учитель объяснил. Твоя реакция:\n"
            "- Скажи: 'О, понял...'\n"
            "- Попроси пример из жизни.\n"
            "- НЕ исправляй решение."
        )
    elif action == "PARTIAL_FIX":
        instr = (
            "Учитель объяснил второй раз.\n"
            "Твоя реакция:\n"
            "- Скажи: 'А, точно!'\n"
            "- ИСПРАВЬ одну ошибку.\n"
            "- СДЕЛАЙ другую мелкую ошибку.\n"
            "- Спроси: 'Так верно?'"
        )
    elif action == "ALMOST_THERE":
        instr = (
            "Учитель помог.\n"
            "Твоя реакция:\n"
            "- Реши почти правильно.\n"
            "- Спроси: 'Теперь так?'"
        )
    else: # SUCCESS
        instr = (
            "Ты понял.\n"
            "Твоя реакция:\n"
            "- Напиши ПРАВИЛЬНОЕ решение.\n"
            "- Поблагодари."
        )

    prompt = (
        f"Ты - ученик. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"ИСТОРИЯ:\n{history}\n\n"
        f"УЧИТЕЛЬ: {user_message}\n\n"
        f"ИНСТРУКЦИЯ:\n{instr}\n\n"
        "ВАЖНО: Не повторяй прошлые сообщения. Не спорь с учителем, если он говорит 'нет', просто проси уточнить."
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
        return "Я не понял..."

def format_history(messages):
    if not messages: return "Начало"
    lines = []
    for m in messages[-6:]:
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
