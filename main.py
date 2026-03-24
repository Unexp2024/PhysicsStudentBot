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
    # Жесткое ограничение сложности
    if cls <= 9:
        complexity_rule = (
            "ВАЖНО: Задача должна быть ОЧЕНЬ ПРОСТОЙ.\n"
            "НЕ используй углы, векторы, синусы, косинусы.\n"
            "Используй только базовые формулы (p=mv, F=ma, I=U/R, A=F*s).\n"
            "Пример: Дана масса и скорость, найти импульс."
        )
    else:
        complexity_rule = "Можно использовать более сложные формулы, но задача должна быть стандартной."

    prompt = (
        f"Ты - ученик {cls} класса. Тема: {topic}.\n"
        f"{complexity_rule}\n\n"
        "Создай задачу и РЕШИ ЕЁ НЕПРАВИЛЬНО.\n\n"
        
        "ТРЕБОВАНИЯ К ОШИБКЕ:\n"
        "- Ошибка должна быть ТИПИЧНОЙ для школьника (перепутал знаки + и *, забыл возвести в квадрат, перепутал буквы).\n"
        "- НЕ пиши физический бред (например, 'импульс равен силе тяжести').\n\n"
        
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
    F = random.choice([10, 20, 50, 100])
    
    # Полный словарь fallbacks на все темы словаря
    fallbacks = {
        7: {
            "механическое движение": f"Машина проехала {s*2} км за {s//10} часов. Найдите скорость.\nМОЁ РЕШЕНИЕ:\n1) v - скорость, s - путь, t - время.\n2) v = t / s (Ошибка!)\n3) v = {s//10} / {s*2} = {round((s//10)/(s*2), 2)}\nОТВЕТ: {round((s//10)/(s*2), 2)} км/ч",
            "скорость": f"Велосипедист едет {s} км со скоростью {v} км/ч. Найдите время.\nМОЁ РЕШЕНИЕ:\n1) t - время, s - путь, v - скорость.\n2) t = s * v (Ошибка!)\n3) t = {s} * {v} = {s*v}\nОТВЕТ: {s*v} ч",
            "плотность": f"Масса тела {m} кг, объём {m*2} м³. Найдите плотность.\nМОЁ РЕШЕНИЕ:\n1) ρ - плотность, m - масса, V - объём.\n2) ρ = m + V (Ошибка!)\n3) ρ = {m} + {m*2} = {m*3}\nОТВЕТ: {m*3} кг/м³",
            "сила тяжести": f"Масса тела {m} кг. Найти силу тяжести (g=10).\nМОЁ РЕШЕНИЕ:\n1) F - сила тяжести.\n2) F = m + 10 (Ошибка!)\n3) F = {m} + 10 = {m+10}\nОТВЕТ: {m+10} Н",
            "давление": f"Сила {F} Н давит на площадь {m} м². Найти давление.\nМОЁ РЕШЕНИЕ:\n1) p - давление, F - сила, S - площадь.\n2) p = F * S (Ошибка!)\n3) p = {F} * {m} = {F*m}\nОТВЕТ: {F*m} Па"
        },
        8: {
            "работа и мощность": f"Ящик передвинули на {s} м с силой {F} Н. Найти работу.\nМОЁ РЕШЕНИЕ:\n1) A - работа.\n2) A = F - s (Ошибка!)\n3) A = {F} - {s} = {abs(F-s)}\nОТВЕТ: {abs(F-s)} Дж",
            "простые механизмы": f"Рычаг. Плечо силы 2 м, сила {F} Н. Момент силы?\nМОЁ РЕШЕНИЕ:\n1) M - момент силы.\n2) M = F + l (Ошибка!)\n3) M = {F} + 2 = {F+2}\nОТВЕТ: {F+2} Н*м",
            "энергия": f"Тело массой {m} кг поднято на высоту {h} м. Потенциальная энергия? (g=10)\nМОЁ РЕШЕНИЕ:\n1) E - энергия.\n2) E = m / h (Ошибка!)\n3) E = {m} / {h} = {round(m/h, 1)}\nОТВЕТ: {round(m/h, 1)} Дж",
            "теплопроводность": f"Нагрели воду массой {m} кг на 10 градусов. Q=? (c=4200)\nМОЁ РЕШЕНИЕ:\n1) Q - теплота.\n2) Q = c - m (Ошибка!)\n3) Q = 4200 - {m} = {4200-m}\nОТВЕТ: {4200-m} Дж"
        },
        9: {
            "ток": f"Напряжение 12 В, сопротивление 4 Ом. Найдите ток.\nМОЁ РЕШЕНИЕ:\n1) I - ток.\n2) I = U + R (Ошибка!)\n3) I = 12 + 4 = 16\nОТВЕТ: 16 А",
            "законы Ньютона": f"Сила {F} Н действует на тело массой {m} кг. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = F + m (Ошибка!)\n3) a = {F} + {m} = {F+m}\nОТВЕТ: {F+m} м/с²",
            "импульс": f"Масса машины {m*100} кг, скорость {v} м/с. Найти импульс.\nМОЁ РЕШЕНИЕ:\n1) p - импульс.\n2) p = m + v (Ошибка!)\n3) p = {m*100} + {v} = {m*100+v}\nОТВЕТ: {m*100+v} кг*м/с",
            "движение": f"Тело разгоняется с ускорением 2 м/с² из состояния покоя. Время 5 с. Скорость?\nМОЁ РЕШЕНИЕ:\n1) v - скорость.\n2) v = a - t (Ошибка!)\n3) v = 2 - 5 = -3\nОТВЕТ: -3 м/с",
            "архимедова сила": f"Тело объёмом {m} м³ в воде (ρ=1000). Сила Архимеда? (g=10)\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = V / ρ (Ошибка!)\n3) F = {m} / 1000 = {m/1000}\nОТВЕТ: {m/1000} Н"
        },
        10: {
             "движение по окружности": f"Радиус {h} м, скорость {v//2} м/с. Ускорение?\nМОЁ РЕШЕНИЕ:\n1) a - ускорение.\n2) a = v + R (Ошибка!)\n3) a = {v//2} + {h} = {v//2+h}\nОТВЕТ: {v//2+h} м/с²",
             "тяготение": f"Масса Земли M, масса тела {m} кг, расстояние R. Формула силы?\nМОЁ РЕШЕНИЕ:\n1) F - сила.\n2) F = G * M * m * R (Ошибка: умножил на R вместо деления!)\nОТВЕТ: Формула неверная.",
             "работа": f"Сила {F} Н, угол 90 градусов, перемещение {s} м. Работа?\nМОЁ РЕШЕНИЕ:\n1) A - работа.\n2) A = F * s (Ошибка: не учел угол!)\n3) A = {F} * {s} = {F*s}\nОТВЕТ: {F*s} Дж"
        },
        11: {
            "термодинамика": f"Газ получил {F*10} Дж тепла, совершил работу {F} Дж. Изменение внутренней энергии?\nМОЁ РЕШЕНИЕ:\n1) U - энергия.\n2) U = Q + A (Ошибка: знак!)\n3) U = {F*10} + {F} = {F*11}\nОТВЕТ: {F*11} Дж"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if not task:
        # Если темы нет в fallback, берем первую попавшуюся из класса
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
            "Учитель ответил нечетко или ушел от ответа.\n"
            "Твоя реакция:\n"
            "1. НЕ упоминай прошлые уроки или прошлые задачи. Живи только текущей задачей.\n"
            "2. Вырази недоумение.\n"
            "3. Спроси прямо: 'Так правильно или нет?'\n"
            "4. НЕ повторяй свои предыдущие сообщения."
        )
    elif action == "ASK_EXAMPLE":
        instr = (
            "Учитель дал хорошее объяснение.\n"
            "Твоя реакция:\n"
            "- Скажи: 'О, теперь понятнее...'\n"
            "- ОБЯЗАТЕЛЬНО попроси пример из жизни.\n"
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

    prompt = (
        f"Ты - ученик. Тема: {topic}.\n"
        f"Твоя задача: {task}\n\n"
        f"ИСТОРИЯ ДИАЛОГА:\n{history}\n\n"
        f"ПОСЛЕДНЕЕ СООБЩЕНИЕ УЧИТЕЛЯ:\n{user_message}\n\n"
        f"ИНСТРУКЦИЯ ДЛЯ ОТВЕТА:\n{instr}\n\n"
        "ВАЖНО: Не повторяй текст своих прошлых сообщений! Не пиши о прошлых уроках."
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
