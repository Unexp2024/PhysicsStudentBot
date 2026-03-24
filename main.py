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

def get_fallback_task(cls, topic):
    # Генерация случайных чисел для подстановки
    v = random.choice([10, 15, 20, 25, 30])
    t = random.choice([2, 3, 4, 5])
    m = random.choice([2, 5, 10])
    h = random.choice([2, 3, 5])
    s = random.choice([10, 20, 50])
    F = random.choice([10, 20, 50])
    U = random.choice([12, 24, 220])
    R = random.choice([2, 5, 10])
    
    # Полный словарь шаблонов на все темы
    fallbacks = {
        7: {
            "механическое движение": f"Поезд проехал {s*10} км за {t} часа. С какой скоростью он двигался?\nМОЁ РЕШЕНИЕ:\n1) v - скорость, s - путь, t - время.\n2) v = t / s (Ошибка: делю время на путь!)\n3) v = {t} / {s*10} = {round(t/(s*10), 2)} км/ч\nОТВЕТ: {round(t/(s*10), 2)} км/ч",
            "скорость": f"Автомобиль двигался со скоростью {v} м/с в течение {t} секунд. Какой путь он прошел?\nМОЁ РЕШЕНИЕ:\n1) s - путь, v - скорость, t - время.\n2) s = v - t (Ошибка: вычитаю!)\n3) s = {v} - {t} = {v-t} м\nОТВЕТ: {v-t} м",
            "плотность": f"Найдите плотность вещества, если масса {m*100} г, а объём {m*50} см³.\nМОЁ РЕШЕНИЕ:\n1) ρ - плотность, m - масса, V - объём.\n2) ρ = m + V (Ошибка: складываю!)\n3) ρ = {m*100} + {m*50} = {m*150} г/см³\nОТВЕТ: {m*150} г/см³",
            "сила тяжести": f"Масса человека {m*10} кг. Какова сила тяжести, действующая на него? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F - сила тяжести.\n2) F = m + 10 (Ошибка: складываю!)\n3) F = {m*10} + 10 = {m*10+10} Н\nОТВЕТ: {m*10+10} Н",
            "давление": f"Тело массой {m} кг стоит на опоре площадью {m} м². Какое давление оно оказывает? (g=10)\nМОЁ РЕШЕНИЕ:\n1) p - давление, F - вес, S - площадь.\n2) p = F * S (Ошибка: умножаю!)\n3) F = {m}*10={m*10}. p = {m*10} * {m} = {m*m*10} Па\nОТВЕТ: {m*m*10} Па"
        },
        8: {
            "работа и мощность": f"Какую работу совершит сила {F} Н при перемещении тела на {s} м?\nМОЁ РЕШЕНИЕ:\n1) A - работа, F - сила, s - путь.\n2) A = F / s (Ошибка: делю!)\n3) A = {F} / {s} = {F//s} Дж\nОТВЕТ: {F//s} Дж",
            "простые механизмы": f"С помощью рычага рабочий поднимает груз массой {m*10} кг. Плечо силы рабочего 2 м, а плечо силы тяжести груза 0.5 м. Какую силу прикладывает рабочий? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l2 / l1 (Ошибка: перепутал плечи!)\n3) F2 = {m*10}*10={m*100} Н. F1 = {m*100} * 0.5 / 2 = {m*25} Н\nОТВЕТ: {m*25} Н",
            "энергия": f"Тело массой {m} кг поднято на высоту {h} м. Какова его потенциальная энергия? (g=10)\nМОЁ РЕШЕНИЕ:\n1) E - энергия.\n2) E = m / h (Ошибка: делю!)\n3) E = {m} / {h} = {round(m/h, 1)} Дж\nОТВЕТ: {round(m/h, 1)} Дж",
            "теплопроводность": f"Сколько теплоты нужно, чтобы нагреть {m} кг воды на 10 градусов? (c=4200)\nМОЁ РЕШЕНИЕ:\n1) Q - теплота.\n2) Q = c - m (Ошибка: вычитаю!)\n3) Q = 4200 - {m} = {4200-m} Дж\nОТВЕТ: {4200-m} Дж"
        },
        9: {
            "законы Ньютона": f"На тело массой {m} кг действует сила {F} Н. Каково ускорение тела?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = F + m (Ошибка: складываю!)\n3) a = {F} + {m} = {F+m} м/с²\nОТВЕТ: {F+m} м/с²",
            "движение": f"Автомобиль разгоняется с ускорением 2 м/с² из состояния покоя. Какой путь он пройдет за {t} с?\nМОЁ РЕШЕНИЕ:\n1) s - путь, a - ускорение, t - время.\n2) s = a * t (Ошибка: забыл делить на 2 и квадрат!)\n3) s = 2 * {t} = {2*t} м\nОТВЕТ: {2*t} м",
            "импульс": f"Мяч массой {m*0.1} кг летит со скоростью {v} м/с. Каков его импульс?\nМОЁ РЕШЕНИЕ:\n1) p - импульс.\n2) p = m + v (Ошибка: складываю!)\n3) p = {m*0.1} + {v} = {m*0.1+v} кг*м/с\nОТВЕТ: {m*0.1+v} кг*м/с",
            "архимедова сила": f"Тело объёмом {m} м³ погружено в воду (ρ=1000 кг/м³). Найти силу Архимеда. (g=10)\nМОЁ РЕШЕНИЕ:\n1) F - сила Архимеда.\n2) F = V + ρ (Ошибка: складываю!)\n3) F = {m} + 1000 = {m+1000} Н\nОТВЕТ: {m+1000} Н",
            "ток": f"Найдите сопротивление проводника, если напряжение {U} В, а сила тока {m} А.\nМОЁ РЕШЕНИЕ:\n1) R - сопротивление.\n2) R = U + I (Ошибка: складываю!)\n3) R = {U} + {m} = {U+m} Ом\nОТВЕТ: {U+m} Ом"
        },
        10: {
            "движение по окружности": f"Автомобиль движется по закруглению радиусом {s} м со скоростью {v} м/с. Найти центростремительное ускорение.\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = v + R (Ошибка: складываю!)\n3) a = {v} + {s} = {v+s} м/с²\nОТВЕТ: {v+s} м/с²",
            "тяготение": f"Ракета поднялась на высоту, равную радиусу Земли. Во сколько раз уменьшилась сила тяжести?\nМОЁ РЕШЕНИЕ:\n1) Сила притяжения обратно пропорциональна расстоянию.\n2) Ответ: в 2 раза. (Ошибка: забыл про квадрат расстояния!)\nОТВЕТ: в 2 раза",
            "законы Кеплера": f"Как относится период обращения планет, если радиус орбиты одной в 2 раза больше другой?\nМОЁ РЕШЕНИЕ:\n1) T~R.\n2) Отношение периодов 1:2. (Ошибка: забыл про степень 3/2!)\nОТВЕТ: 1:2",
            "работа": f"Тело массой {m} кг движется со скоростью {v} м/с. Какова его кинетическая энергия?\nМОЁ РЕШЕНИЕ:\n1) E - энергия.\n2) E = m * v (Ошибка: забыл квадрат и деление!)\n3) E = {m} * {v} = {m*v} Дж\nОТВЕТ: {m*v} Дж"
        },
        11: {
            "молекулярно-кинетическая теория": f"Как изменится давление газа, если концентрацию молекул увеличить в 2 раза?\nМОЁ РЕШЕНИЕ:\n1) p ~ n.\n2) Давление уменьшится в 2 раза. (Ошибка: перепутал зависимость!)\nОТВЕТ: Уменьшится в 2 раза",
            "термодинамика": f"Газ получил {F*10} Дж теплоты и совершил работу {F} Дж. Чему равно изменение внутренней энергии?\nМОЁ РЕШЕНИЕ:\n1) U = Q - A.\n2) U = Q + A. (Ошибка: знак!)\n3) U = {F*10} + {F} = {F*11} Дж\nОТВЕТ: {F*11} Дж",
            "электрическое поле": f"Напряженность поля {F} Н/Кл. Какая сила действует на заряд {m} Кл?\nМОЁ РЕШЕНИЕ:\n1) F = E * q.\n2) F = E / q. (Ошибка: делю!)\n3) F = {F} / {m} = {F//m} Н\nОТВЕТ: {F//m} Н",
            "магнитное поле": f"Сила тока {m} А, индукция поля {v} Тл, длина проводника {h} м. Найти силу Ампера.\nМОЁ РЕШЕНИЕ:\n1) F = B * I * L.\n2) F = B + I + L. (Ошибка: складываю!)\n3) F = {v} + {m} + {h} = {v+m+h} Н\nОТВЕТ: {v+m+h} Н",
            "колебания": f"Математический маятник имеет длину {h} м. Найти период колебаний. (g=10)\nМОЁ РЕШЕНИЕ:\n1) T = 2π * l / g. (Ошибка: забыл корень!)\n3) T = 6.28 * {h} / 10 = {round(6.28*h/10, 1)} с\nОТВЕТ: {round(6.28*h/10, 1)} с"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
        # Fallback на случай опечатки в ключах
        if class_tasks:
            task = list(class_tasks.values())[0]
        else:
            task = f"Задача по теме {topic}. Масса {m} кг. Найти силу. F = m + 10 = {m+10} Н."
            
    return task

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    # Используем ТОЛЬКО надежные шаблоны, чтобы избежать бреда ИИ
    task = get_fallback_task(cls, topic)
        
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
    
    # Жесткие инструкции, запрещающие "литературщину"
    if action == "STAY_CONFUSED":
        instr = "Учитель не ответил. Спроси: 'Так это правильный ответ или нет?'."
    elif action == "ASK_EXAMPLE":
        instr = "Попроси пример из жизни. Не исправляй решение."
    elif action == "PARTIAL_FIX":
        instr = "Скажи 'А, точно!'. Исправь ОДНУ ошибку, сделай другую. Спроси 'Так верно?'."
    elif action == "ALMOST_THERE":
        instr = "Реши почти правильно. Спроси 'Теперь так?'."
    else: 
        instr = "Реши ПРАВИЛЬНО. Поблагодари."

    prompt = (
        f"ТЫ — школьник. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"ИСТОРИЯ:\n{history}\n\n"
        f"УЧИТЕЛЬ: {user_message}\n\n"
        f"ЗАДАНИЕ: {instr}\n\n"
        
        "ПРАВИЛА:\n"
        "1. Пиши ТОЛЬКО свою фразу.\n"
        "2. НЕ пиши 'Учитель:', 'Я:' или описания действий в скобках.\n"
        "3. Просто ответь словами школьника."
    )

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b", max_tokens=500, temperature=0.7
        )
        result = response.choices[0].message.content.strip()
        
        # Удаляем мусор, если модель все же сгенерировала сценарий
        if result.startswith("Учитель:") or result.startswith("Я:"):
            # Берем текст после последнего двоеточия
            parts = result.split(":")
            result = parts[-1].strip()
        # Удаляем текст в скобках в начале строки (описание действий)
        if result.startswith("("):
             result = re.sub(r"^\([^)]*\)\s*", "", result)
             
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
