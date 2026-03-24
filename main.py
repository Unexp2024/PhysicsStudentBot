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
    # Переменные для более сложных задач
    v_kmh = random.choice([36, 54, 72]) # км/ч
    v_ms = random.choice([10, 15, 20])  # м/с
    t_min = random.choice([5, 10, 20])  # минуты
    t_h = random.choice([0.5, 2, 3])    # часы
    m_kg = random.choice([500, 1500, 3000]) # кг (для машин)
    m_g = random.choice([200, 500, 1000])   # граммы
    m_t = random.choice([2, 5, 10])         # тонны
    h_m = random.choice([5, 10, 20])        # метры
    s_m = random.choice([100, 500, 1000])   # метры
    s_km = random.choice([30, 60, 90])      # км
    F_N = random.choice([100, 500, 1000])
    U_V = random.choice([220, 110, 12])
    R_Om = random.choice([10, 20, 50])
    
    fallbacks = {
        7: {
            "механическое движение": 
                f"УСЛОВИЕ: Автомобиль двигался равномерно и проехал расстояние {s_km} км за время {t_h} часа. С какой скоростью двигался автомобиль?\n"
                f"МОЁ РЕШЕНИЕ:\n1) v — скорость, s — путь, t — время.\n2) Формула: v = t / s.\n3) v = {t_h} / {s_km} = {round(t_h/s_km, 2)} км/ч.\nОТВЕТ: {round(t_h/s_km, 2)} км/ч.",
            
            "скорость": 
                f"УСЛОВИЕ: Поезд движется со скоростью {v_kmh} км/ч. Какой путь он пройдёт за {t_min} минут? (Ответ дайте в километрах).\n"
                f"МОЁ РЕШЕНИЕ:\n1) s — путь, v — скорость, t — время.\n2) t = {t_min} минут. Сразу подставляю: s = v * t.\n3) s = {v_kmh} * {t_min} = {v_kmh * t_min} км.\nОТВЕТ: {v_kmh * t_min} км.",
            
            "плотность": 
                f"УСЛОВИЕ: Металлическая деталь имеет массу {m_g} г и объём {m_g//4} см³. Определите плотность металла, из которого изготовлена деталь.\n"
                f"МОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём.\n2) Формула: ρ = m + V.\n3) ρ = {m_g} + {m_g//4} = {m_g + m_g//4} г/см³.\nОТВЕТ: {m_g + m_g//4} г/см³.",
            
            "сила тяжести": 
                f"УСЛОВИЕ: Масса груза составляет {m_kg} кг. Найдите силу тяжести, действующую на груз. Ускорение свободного падения g = 10 Н/кг.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила тяжести.\n2) F = m + g.\n3) F = {m_kg} + 10 = {m_kg + 10} Н.\nОТВЕТ: {m_kg + 10} Н.",
            
            "давление": 
                f"УСЛОВИЕ: Трактор массой {m_t*1000} кг стоит на дороге. Площадь опоры его гусениц равна {m_t*2} м². Вычислите давление, оказываемое трактором на дорогу. (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — давление, F — вес, S — площадь.\n2) F = m * g = {m_t*1000} * 10 = {m_t*10000} Н.\n3) p = F * S = {m_t*10000} * {m_t*2} = {m_t*10000 * m_t*2} Па.\nОТВЕТ: {m_t*10000 * m_t*2} Па."
        },
        8: {
            "работа и мощность": 
                f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т на высоту {h_m} м. Какую работу совершает кран? (g=10 Н/кг).\n"
                f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m (ошибка: забыл умножить на g). s = {h_m}.\n3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\nОТВЕТ: {m_t * h_m} Дж.",
            
            "простые механизмы": 
                f"УСЛОВИЕ: При помощи рычага рабочий поднимает камень массой 300 кг. Расстояние от точки опоры до камня 0.5 м, а до руки рабочего — 3 м. Какую силу должен приложить рабочий? (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2.\n3) F2 = 300 * 10 = 3000 Н. F1 = 3000 * 3 / 0.5 = 18000 Н.\nОТВЕТ: 18000 Н.",
            
            "энергия": 
                f"УСЛОВИЕ: Птица массой 2 кг летит на высоте {h_m} м со скоростью {v_ms} м/с. Определите её кинетическую энергию.\n"
                f"МОЁ РЕШЕНИЕ:\n1) Eк — кинетическая энергия.\n2) Eк = m * h.\n3) Eк = 2 * {h_m} = {2 * h_m} Дж.\nОТВЕТ: {2 * h_m} Дж.",
            
            "теплопроводность": 
                f"УСЛОВИЕ: Сколько энергии потребуется, чтобы нагреть воду массой {m_g//100} кг от 20°С до кипения? (c = 4200 Дж/(кг*°С)).\n"
                f"МОЁ РЕШЕНИЕ:\n1) Q — количество теплоты.\n2) Q = c * m (забыл температуру).\n3) Q = 4200 * {m_g//100} = {4200 * (m_g//100)} Дж.\nОТВЕТ: {4200 * (m_g//100)} Дж."
        },
        9: {
            "законы Ньютона": 
                f"УСЛОВИЕ: Автомобиль массой {m_kg} кг разгоняется с ускорением 2 м/с². Найдите равнодействующую силу, действующую на автомобиль.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, a — ускорение.\n2) F = m + a.\n3) F = {m_kg} + 2 = {m_kg + 2} Н.\nОТВЕТ: {m_kg + 2} Н.",
            
            "движение": 
                f"УСЛОВИЕ: Поезд тормозит с ускорением 0.5 м/с². Начальная скорость была 36 км/ч (10 м/с). Какой путь пройдет поезд до остановки?\n"
                f"МОЁ РЕШЕНИЕ:\n1) S — путь, v — скорость, a — ускорение.\n2) S = v / a.\n3) S = 10 / 0.5 = 20 м.\nОТВЕТ: 20 м.",
            
            "импульс": 
                f"УСЛОВИЕ: Мяч массой 0.5 кг летит со скоростью 10 м/с. Найдите его импульс.\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0.5 + 10 = 10.5 кг*м/с.\nОТВЕТ: 10.5 кг*м/с.",
            
            "ток": 
                f"УСЛОВИЕ: Электрическая лампа включена в сеть напряжением {U_V} В. Сила тока в ней {R_Om//10} А. Найдите сопротивление лампы.\n"
                f"МОЁ РЕШЕНИЕ:\n1) R — сопротивление, U — напряжение, I — ток.\n2) R = U + I.\n3) R = {U_V} + {R_Om//10} = {U_V + R_Om//10} Ом.\nОТВЕТ: {U_V + R_Om//10} Ом."
        },
        10: {
             "движение по окружности": 
                f"УСЛОВИЕ: Трамвайный вагон движется по закруглению радиусом {s_m} м со скоростью {v_ms} м/с. Определите центростремительное ускорение.\n"
                f"МОЁ РЕШЕНИЕ:\n1) a — ускорение, v — скорость, R — радиус.\n2) a = v + R.\n3) a = {v_ms} + {s_m} = {v_ms + s_m} м/с².\nОТВЕТ: {v_ms + s_m} м/с².",
                 
             "работа": 
                f"УСЛОВИЕ: Груз массой 100 кг поднимают равноускоренно на высоту {h_m} м за 2 секунды. Найдите работу силы тяги. (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) A = F * s.\n2) F = m * g.\n3) A = 100 * 10 * {h_m} = {1000 * h_m} Дж (ошибка: не учтено ускорение).\nОТВЕТ: {1000 * h_m} Дж."
        },
        11: {
            "термодинамика": 
                f"УСЛОВИЕ: Идеальный газ совершил работу 500 Дж, получив количество теплоты 800 Дж. Как изменилась внутренняя энергия газа?\n"
                f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, A — работа, Q — теплота.\n2) ΔU = A + Q (ошибка: знаки).\n3) ΔU = 500 + 800 = 1300 Дж.\nОТВЕТ: 1300 Дж.",
            
            "магнитное поле": 
                f"УСЛОВИЕ: Проводник длиной 0.5 м с током 4 А находится в магнитном поле индукцией 0.2 Тл. Найдите силу Ампера (проводник перпендикулярен линиям поля).\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила Ампера, B — индукция, I — ток, L — длина.\n2) F = B + I + L.\n3) F = 0.2 + 4 + 0.5 = 4.7 Н.\nОТВЕТ: 4.7 Н."
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
        if class_tasks: task = list(class_tasks.values())[0]
        else: task = f"Задача по теме {topic}. Масса {m_kg} кг. F = m + 10 = {m_kg+10} Н."
            
    return task

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task

def check_teacher_quality(message):
    lower_msg = message.lower()
    # Список слов, которые часто означают "учитель не помог"
    bad_markers = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси", "сомневаюсь", "думаю", "непонятно", "подожди", "минуту", "сейчас", "погоди", "молодец", "умница", "нет", "вряд ли", "неверно"]
    
    word_count = len(message.split())
    
    # Если сообщение короткое и содержит негативный маркер -> плохой ответ
    # Порог увеличен до 25 слов, чтобы отсеять длинные "философские" нерелевантные ответы
    if any(marker in lower_msg for marker in bad_markers) and word_count < 25:
        return False

    # LLM проверка для остальных случаев
    prompt = (
        f"Ученик решил задачу и спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n\n"
        "Оцени качество ответа учителя.\n"
        "КРИТЕРИЙ: Учитель должен явно указать на ошибку в формуле или дать правильный алгоритм.\n"
        "Если учитель просто хвалит, философствует или говорит 'нет' без объяснения — это false.\n"
        "Ответь ТОЛЬКО JSON: {\"is_relevant\": true/false}"
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
    
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель НЕ объяснил ошибку (просто сказал 'нет', 'вряд ли' или ушел от ответа).\n"
            "Твоя реакция:\n"
            "1. Ты УВЕРЕН в своём решении.\n"
            "2. Удивись, почему учитель не согласен.\n"
            "3. Попроси назвать КОНКРЕТНУЮ ошибку.\n"
            "4. НЕ пересчитывай и НЕ используй правильные формулы."
        )
    elif action == "ASK_EXAMPLE":
        instr = "Учитель указал на ошибку. Скажи 'О, понял...' и попроси пример из жизни. Не исправляй решение."
    elif action == "PARTIAL_FIX":
        instr = "Учитель привел пример. Скажи 'А, точно!'. Исправь формулу, но ошибись в арифметике. Спроси 'Так правильно?'."
    elif action == "ALMOST_THERE":
        instr = "Реши почти правильно, ошибись в единицах измерения. Спроси 'Верно?'."
    else: 
        instr = "Реши ПРАВИЛЬНО. Поблагодари."

    prompt = (
        f"ТЫ — школьник. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"Учитель написал: \"{user_message}\"\n\n"
        f"Твоя цель: {instr}\n\n"
        "ПРАВИЛА:\n"
        "1. Пиши очень коротко.\n"
        "2. Пиши только свой текст.\n"
        "3. Не рассуждай о физике."
    )

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b", max_tokens=300, temperature=0.7
        )
        result = response.choices[0].message.content.strip()
        
        if result.startswith("Учитель:") or result.startswith("Я:"):
            parts = result.split(":")
            result = parts[-1].strip()
        if result.startswith("("):
             result = re.sub(r"^\([^)]*\)\s*", "", result)
             
        return result
    except Exception as e:
        logger.error(f"Gen error: {e}")
        return "Я не понял."

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
