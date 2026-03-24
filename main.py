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
    # Переменные для генерации
    v = random.choice([10, 15, 20])
    t = random.choice([2, 3, 5])
    m = random.choice([2, 5, 10])
    h = random.choice([2, 3, 5])
    s = random.choice([10, 20, 50])
    F = random.choice([10, 20, 50])
    U = random.choice([12, 24])
    R = random.choice([2, 5, 10])
    I = random.choice([2, 5])
    B = random.choice([0.5, 1, 2])
    L = random.choice([0.5, 1, 2])
    q = random.choice([1, 2, 5])
    
    # Обновленные шаблоны с развернутыми условиями
    fallbacks = {
        7: {
            "механическое движение": 
                f"УСЛОВИЕ: Поезд движется равномерно между двумя городами. Расстояние между ними составляет {s*10} км. Поезд преодолел это расстояние за {t} часа. Определите скорость движения поезда.\n"
                f"МОЁ РЕШЕНИЕ:\n1) v — скорость, s — путь, t — время.\n2) Формула скорости: v = t / s.\n3) v = {t} / {s*10} = {round(t/(s*10), 2)} км/ч.\nОТВЕТ: {round(t/(s*10), 2)} км/ч.",
            
            "скорость": 
                f"УСЛОВИЕ: Автомобиль движется по шоссе с постоянной скоростью {v} м/с. Какое расстояние он преодолеет за 5 секунд движения?\n"
                f"МОЁ РЕШЕНИЕ:\n1) s — путь, v — скорость.\n2) s = v - 5 (Ошибка: вычитание!).\n3) s = {v} - 5 = {v-5} м.\nОТВЕТ: {v-5} м.",
            
            "плотность": 
                f"УСЛОВИЕ: В лаборатории провели измерения бруска. Его масса составила {m*100} г, а объём — {m*50} см³. Вычислите плотность вещества, из которого сделан брусок.\n"
                f"МОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём.\n2) Формула: ρ = m + V.\n3) ρ = {m*100} + {m*50} = {m*150} г/см³.\nОТВЕТ: {m*150} г/см³.",
            
            "сила тяжести": 
                f"УСЛОВИЕ: Тело массой {m*10} кг находится вблизи поверхности Земли. Определите силу тяжести, действующую на это тело, если ускорение свободного падения g = 10 Н/кг.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила тяжести, m — масса.\n2) Формула: F = m + g.\n3) F = {m*10} + 10 = {m*10+10} Н.\nОТВЕТ: {m*10+10} Н.",
            
            "давление": 
                f"УСЛОВИЕ: На горизонтальную поверхность площадью {m} м² действует сила {F} Н, направленная перпендикулярно поверхности. Найдите давление, оказываемое этой силой.\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — давление, F — сила, S — площадь.\n2) p = F * S.\n3) p = {F} * {m} = {F*m} Па.\nОТВЕТ: {F*m} Па."
        },
        8: {
            "работа и мощность": 
                f"УСЛОВИЕ: Рабочий толкает тележку, прикладывая горизонтальную силу {F} Н. Тележка переместилась на расстояние {s} м. Вычислите работу, совершённую рабочим.\n"
                f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — путь.\n2) A = F / s.\n3) A = {F} / {s} = {F//s} Дж.\nОТВЕТ: {F//s} Дж.",
            
            "простые механизмы": 
                f"УСЛОВИЕ: На левое плечо рычага длиной 2 м действует сила, а на правое плечо длиной 0.5 м подвешен груз массой 50 кг. Какую силу нужно приложить к левому плечу, чтобы рычаг находился в равновесии? (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) Правило рычага: F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2. (Ошибка: перепутал плечи!).\n3) F2 = 500 Н. F1 = 500 * 2 / 0.5 = 2000 Н.\nОТВЕТ: 2000 Н.",
            
            "энергия": 
                f"УСЛОВИЕ: Яблоко массой {m} кг висит на ветке на высоте {h} м от земли. Чему равна потенциальная энергия яблока? (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) E — потенциальная энергия.\n2) E = m / h.\n3) E = {m} / {h} = {round(m/h,1)} Дж.\nОТВЕТ: {round(m/h,1)} Дж.",
            
            "теплопроводность": 
                f"УСЛОВИЕ: Для нагревания {m} кг воды на 10 градусов Цельсия потребовалось некоторое количество теплоты. Удельная теплоёмкость воды 4200 Дж/(кг*°С). Найдите количество теплоты.\n"
                f"МОЁ РЕШЕНИЕ:\n1) Q — количество теплоты.\n2) Q = c - m.\n3) Q = 4200 - {m} = {4200-m} Дж.\nОТВЕТ: {4200-m} Дж."
        },
        9: {
            "законы Ньютона": 
                f"УСЛОВИЕ: На тело массой {m} кг действует постоянная сила {F} Н. Определите ускорение, с которым движется это тело.\n"
                f"МОЁ РЕШЕНИЕ:\n1) a — ускорение, F — сила, m — масса.\n2) a = F + m.\n3) a = {F} + {m} = {F+m} м/с².\nОТВЕТ: {F+m} м/с².",
            
            "движение": 
                f"УСЛОВИЕ: Велосипедист двигался со скоростью 10 м/с в течение {t} секунд. Какой путь он проехал за это время?\n"
                f"МОЁ РЕШЕНИЕ:\n1) s — путь, v — скорость.\n2) s = v - t.\n3) s = 10 - {t} = {10-t} м.\nОТВЕТ: {10-t} м.",
            
            "импульс": 
                f"УСЛОВИЕ: Мяч массой {m} кг летит горизонтально со скоростью {v} м/с. Чему равен импульс мяча?\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = {m} + {v} = {m+v} кг*м/с.\nОТВЕТ: {m+v} кг*м/с.",
            
            "архимедова сила": 
                f"УСЛОВИЕ: Камень объёмом {m} м³ полностью погружен в воду (плотность воды 1000 кг/м³). Вычислите выталкивающую силу, действующую на камень. (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила Архимеда.\n2) F = V + 1000.\n3) F = {m} + 1000 = {m+1000} Н.\nОТВЕТ: {m+1000} Н.",
            
            "ток": 
                f"УСЛОВИЕ: К резистору сопротивлением {R} Ом приложено напряжение {U} В. Какова сила тока, протекающего через резистор?\n"
                f"МОЁ РЕШЕНИЕ:\n1) I — сила тока, U — напряжение, R — сопротивление.\n2) I = U + R.\n3) I = {U} + {R} = {U+R} А.\nОТВЕТ: {U+R} А."
        },
        10: {
             "движение по окружности": 
                f"УСЛОВИЕ: Автомобиль движется по закруглению дороги радиусом {h} м с постоянной скоростью {v} м/с. Найдите центростремительное ускорение автомобиля.\n"
                f"МОЁ РЕШЕНИЕ:\n1) a — ускорение, v — скорость, R — радиус.\n2) a = v + R.\n3) a = {v} + {h} = {v+h} м/с².\nОТВЕТ: {v+h} м/с².",
             
             "тяготение": 
                f"УСЛОВИЕ: Искусственный спутник Земли находится на некоторой высоте. Масса Земли M. Запишите формулу для расчета силы гравитационного притяжения, действующей на спутник массой {m} кг.\n"
                f"МОЁ РЕШЕНИЕ:\n1) Закон всемирного тяготения.\n2) F = G * M * m * R (Ошибка: умножение вместо деления!).\nОТВЕТ: Формула неверная.",
                 
             "работа": 
                f"УСЛОВИЕ: Груз массой {m} кг равномерно поднимают на высоту {h} м. Вычислите работу, совершаемую при этом. (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) A — работа.\n2) A = m - h.\n3) A = {m} - {h} = {m-h} Дж.\nОТВЕТ: {m-h} Дж."
        },
        11: {
            "термодинамика": 
                f"УСЛОВИЕ: Идеальный газ получил от нагревателя {F*100} Дж теплоты и совершил работу {F*10} Дж. Как изменилась внутренняя энергия газа?\n"
                f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, Q — теплота, A — работа.\n2) ΔU = Q + A (Ошибка: знак работы!).\n3) ΔU = {F*100} + {F*10} = {F*110} Дж.\nОТВЕТ: {F*110} Дж.",
            
            "электрическое поле": 
                f"УСЛОВИЕ: В электрическое поле напряженностью {F} Н/Кл поместили заряд {q} Кл. Определите силу, действующую на этот заряд.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила, E — напряженность.\n2) F = E + q.\n3) F = {F} + {q} = {F+q} Н.\nОТВЕТ: {F+q} Н.",
            
            "магнитное поле": 
                f"УСЛОВИЕ: Проводник длиной {L} м с током {I} А помещен в магнитное поле с индукцией {B} Тл перпендикулярно линиям поля. Найдите силу Ампера.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила Ампера.\n2) F = B + I + L.\n3) F = {B} + {I} + {L} = {round(B+I+L,2)} Н.\nОТВЕТ: {round(B+I+L,2)} Н.",
            
            "колебания": 
                f"УСЛОВИЕ: Математический маятник имеет длину {L} м. Рассчитайте период его колебаний. (g=10 м/с², π≈3.14)\n"
                f"МОЁ РЕШЕНИЕ:\n1) T — период.\n2) T = 2π * (L + g). (Ошибка: формула неверна!).\n3) T = 6.28 * ({L} + 10) = {round(6.28*(L+10),1)} с.\nОТВЕТ: {round(6.28*(L+10),1)} с."
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
        if class_tasks: task = list(class_tasks.values())[0]
        else: task = f"Задача по теме {topic}. Масса {m} кг. F = m + 10 = {m+10} Н."
            
    return task

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task

def check_teacher_quality(message):
    lower_msg = message.lower()
    # Список слов-маркеров, которые часто встречаются в нерелевантных ответах
    bad_markers = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси", "сомневаюсь", "думаю", "непонятно", "подожди", "минуту", "сейчас", "погоди"]
    
    word_count = len(message.split())
    
    # Если есть маркер И сообщение короткое -> точно плохой ответ
    if any(marker in lower_msg for marker in bad_markers) and word_count < 20:
        return False

    # Если сообщение слишком короткое -> плохой ответ
    if word_count < 5:
        return False

    # Строгая LLM проверка для длинных сообщений
    prompt = (
        f"Ученик решил задачу и спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n\n"
        "Оцени качество ответа учителя по критерию ПОЛЕЗНОСТИ для исправления ошибки.\n"
        "КРИТЕРИЙ: Учитель должен явно указать на ошибку в формуле, предложить правильную формулу или указать на конкретную арифметическую ошибку.\n"
        "Если учитель просто философствует на тему физики, пишет общие слова ('подумай о природе вещей'), уходит от ответа или пишет ерунду — это false.\n"
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
            "Учитель не указал на ошибку. Он ушел от ответа или написал общие фразы.\n"
            "Твоя реакция:\n"
            "1. Ты УВЕРЕН в своём решении.\n"
            "2. Удивись, почему он не говорит прямо.\n"
            "3. Спроси: 'Так это правильный ответ или нет?'\n"
            "4. Не исправляй решение."
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
        "1. Пиши коротко и просто.\n"
        "2. Пиши только свой текст.\n"
        "3. Не пиши 'Учитель:', 'Я:', скобки."
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
