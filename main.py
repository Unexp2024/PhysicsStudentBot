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
    I = random.choice([2, 5]) # Ток
    B = random.choice([0.5, 1, 2]) # Индукция
    L = random.choice([0.5, 1, 2]) # Длина проводника
    q = random.choice([1, 2, 5]) # Заряд
    
    # Полный словарь шаблонов (добавлен 11 класс и исправлены остальные)
    fallbacks = {
        7: {
            "механическое движение": f"Поезд проехал {s*10} км за {t} часа. С какой скоростью он двигался?\nМОЁ РЕШЕНИЕ:\n1) v - скорость.\n2) v = t / s\n3) v = {t} / {s*10} = {round(t/(s*10), 2)} км/ч\nОТВЕТ: {round(t/(s*10), 2)} км/ч",
            "скорость": f"Автомобиль двигался со скоростью {v} м/с в течение 5 с. Какой путь он прошел?\nМОЁ РЕШЕНИЕ:\n1) s - путь.\n2) s = v - 5\n3) s = {v} - 5 = {v-5} м\nОТВЕТ: {v-5} м",
            "плотность": f"Масса тела {m*100} г, объём {m*50} см³. Найти плотность.\nМОЁ РЕШЕНИЕ:\n1) ρ - плотность.\n2) ρ = m + V\n3) ρ = {m*100} + {m*50} = {m*150} г/см³\nОТВЕТ: {m*150} г/см³",
            "сила тяжести": f"Масса тела {m*10} кг. Найти силу тяжести (g=10).\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = m + 10\n3) F = {m*10} + 10 = {m*10+10} Н\nОТВЕТ: {m*10+10} Н",
            "давление": f"Сила {F} Н давит на площадь {m} м². Найти давление.\nМОЁ РЕШЕНИЕ:\n1) p - давление.\n2) p = F * S\n3) p = {F} * {m} = {F*m} Па\nОТВЕТ: {F*m} Па"
        },
        8: {
            "работа и мощность": f"Сила {F} Н переместила тело на {s} м. Найти работу.\nМОЁ РЕШЕНИЕ:\n1) A - работа.\n2) A = F / s\n3) A = {F} / {s} = {F//s} Дж\nОТВЕТ: {F//s} Дж",
            "простые механизмы": f"Рычаг. Плечо 1 равно 2 м, плечо 2 равно 0.5 м. Груз массой 50 кг висит на плече 2. Какую силу надо приложить к плечу 1? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2.\n3) F2 = 500 Н. F1 = 500 * 2 / 0.5 = 2000 Н.\nОТВЕТ: 2000 Н",
            "энергия": f"Тело массой {m} кг подняли на {h} м. Энергия? (g=10)\nМОЁ РЕШЕНИЕ:\n1) E - энергия.\n2) E = m / h\n3) E = {m} / {h} = {round(m/h,1)} Дж\nОТВЕТ: {round(m/h,1)} Дж",
            "теплопроводность": f"Нагрели {m} кг воды на 10 градусов. Q=? (c=4200)\nМОЁ РЕШЕНИЕ:\n1) Q - теплота.\n2) Q = c - m\n3) Q = 4200 - {m} = {4200-m} Дж\nОТВЕТ: {4200-m} Дж"
        },
        9: {
            "законы Ньютона": f"Сила {F} Н действует на тело {m} кг. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = F + m\n3) a = {F} + {m} = {F+m} м/с²\nОТВЕТ: {F+m} м/с²",
            "движение": f"Скорость 10 м/с, время {t} с. Путь?\nМОЁ РЕШЕНИЕ:\n1) s - путь.\n2) s = v - t\n3) s = 10 - {t} = {10-t} м\nОТВЕТ: {10-t} м",
            "импульс": f"Масса {m} кг, скорость {v} м/с. Импульс?\nМОЁ РЕШЕНИЕ:\n1) p - импульс.\n2) p = m + v\n3) p = {m} + {v} = {m+v}\nОТВЕТ: {m+v} кг*м/с",
            "архимедова сила": f"Объем тела {m} м³, плотность воды 1000 кг/м³. Сила Архимеда? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = V + 1000\n3) F = {m} + 1000 = {m+1000} Н\nОТВЕТ: {m+1000} Н",
            "ток": f"Напряжение {U} В, сопротивление {R} Ом. Ток?\nМОЁ РЕШЕНИЕ:\n1) I - ток.\n2) I = U + R\n3) I = {U} + {R} = {U+R} А\nОТВЕТ: {U+R} А"
        },
        10: {
             "движение по окружности": f"Радиус {h} м, скорость {v} м/с. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = v + R\n3) a = {v} + {h} = {v+h} м/с²\nОТВЕТ: {v+h} м/с²",
             "тяготение": f"Масса Земли M, масса тела {m} кг. Формула силы?\nМОЁ РЕШЕНИЕ:\n1) F = G * M * m / R\n2) Ответ: F = G * M * m * R (Ошибка: умножил на R!)\nОТВЕТ: Формула неверная",
             "работа": f"Тело массой {m} кг подняли на {h} м. Работа? (g=10)\nМОЁ РЕШЕНИЕ:\n1) A - работа.\n2) A = m - h\n3) A = {m} - {h} = {m-h} Дж\nОТВЕТ: {m-h} Дж"
        },
        11: {
            "молекулярно-кинетическая теория": f"Давление газа {F} Па, концентрация молекул {m}*10^25 м^-3. Найти среднюю кинетическую энергию.\nМОЁ РЕШЕНИЕ:\n1) E - энергия.\n2) p = E + n (Ошибка: сложение!)\n3) E = {F} + {m}*10^25 = очень много Дж\nОТВЕТ: {F+m} Дж",
            "термодинамика": f"Газ получил {F*100} Дж теплоты и совершил работу {F*10} Дж. Изменение внутренней энергии?\nМОЁ РЕШЕНИЕ:\n1) U - энергия.\n2) U = Q + A (Ошибка: знак!)\n3) U = {F*100} + {F*10} = {F*110} Дж\nОТВЕТ: {F*110} Дж",
            "электрическое поле": f"Заряд {q} Кл в поле напряженностью {F} Н/Кл. Сила?\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = E + q (Ошибка: сложение!)\n3) F = {F} + {q} = {F+q} Н\nОТВЕТ: {F+q} Н",
            "магнитное поле": f"Проводник длиной {L} м с током {I} А в поле индукцией {B} Тл. Сила Ампера? (Угол 90)\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = B + I + L (Ошибка: сложение вместо умножения!)\n3) F = {B} + {I} + {L} = {round(B+I+L,2)} Н\nОТВЕТ: {round(B+I+L,2)} Н",
            "колебания": f"Длина маятника {L} м. Период? (g=10)\nМОЁ РЕШЕНИЕ:\n1) T - период.\n2) T = 2 * 3.14 * (L + g) (Ошибка: забыл корень и сложил!)\n3) T = 6.28 * ({L} + 10) = {round(6.28*(L+10),1)} с\nОТВЕТ: {round(6.28*(L+10),1)} с"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    # Если темы вдруг не оказалось - берем первую из класса
    if not task:
        if class_tasks: 
            task = list(class_tasks.values())[0]
        else: 
            task = f"Задача по теме {topic}. Масса {m} кг. Найти силу. F = m + 10 = {m+10} Н."
            
    return task

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
            f"Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task

def check_teacher_quality(message):
    lower_msg = message.lower()
    # Список слов, означающих "учитель не ответил"
    bad_markers = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси", "сомневаюсь", "думаю", "непонятно", "подожди", "минуту"]
    
    word_count = len(message.split())
    
    # Если есть маркер и сообщение короткое (< 20 слов) -> плохой ответ
    if any(marker in lower_msg for marker in bad_markers) and word_count < 20:
        return False

    # Если сообщение совсем короткое -> плохой ответ
    if word_count < 5:
        return False

    # Иначе спрашиваем LLM
    prompt = (
        f"Ученик спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n"
        "Является ли этот ответ ПОЛЕЗНЫМ объяснением ошибки? (Есть ли там формула или правильный ход?)\n"
        "Ответь только JSON: {\"is_relevant\": true/false}"
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
    
    # Инструкции
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель НЕ объяснил ошибку и уклонился от ответа.\n"
            "Твоя реакция:\n"
            "1. Ты УВЕРЕН в своем решении.\n"
            "2. Удивись, почему учитель не говорит 'да' или 'нет'.\n"
            "3. Спроси прямо: 'Так это правильный ответ или нет? Я же всё по формуле сделал!'\n"
            "4. НЕ критикуй своё решение и НЕ сомневайся в нём."
        )
    elif action == "ASK_EXAMPLE":
        instr = (
            "Учитель наконец объяснил, в чем ошибка.\n"
            "Твоя реакция:\n"
            "1. Скажи: 'О, я понял...'\n"
            "2. Попроси пример из жизни.\n"
            "3. Не исправляй решение."
        )
    elif action == "PARTIAL_FIX":
        instr = (
            "Учитель привел пример.\n"
            "Твоя реакция:\n"
            "1. Скажи: 'А, теперь понятно!'\n"
            "2. Исправь формулу.\n"
            "3. Сделай новую ошибку в вычислениях.\n"
            "4. Спроси: 'А так правильно?'"
        )
    elif action == "ALMOST_THERE":
        instr = "Реши почти правильно, но ошибись в единицах измерения. Спроси 'Так верно?'."
    else: 
        instr = "Реши ПРАВИЛЬНО. Поблагодари."

    prompt = (
        f"ТЫ — школьник. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"Последнее сообщение учителя: \"{user_message}\"\n\n"
        f"Твоя цель сейчас: {instr}\n\n"
        
        "ПРАВИЛА:\n"
        "1. Пиши коротко.\n"
        "2. Пиши только свою фразу.\n"
        "3. Не пиши 'Учитель:', 'Я:', скобки.\n"
        "4. Не рассуждай логически над своей ошибкой, ты же школьник, ты думаешь, что ты прав."
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
