import os
import json
import random
import logging
import requests
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

logger.info(f"TELEGRAM_TOKEN загружен: {TELEGRAM_TOKEN[:10]}...")

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

# Хранилище сессий
user_sessions = {}

def get_random_class_and_topic():
    """Выбирает случайный класс и тему"""
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def generate_task_with_mistakes(cls, topic):
    """
    Генератор задач (ИИ №1) — Более строгий промт
    """
    # Выбираем тип ошибки заранее, чтобы навести модель на конкретику
    error_type = random.choice([
        "перепутал умножение и деление", 
        "забыл возвести в квадрат", 
        "перепутал буквы в формуле",
        "неправильно перевел единицы измерения"
    ])

    prompt = f"""Ты — генератор задач по физике для {cls} класса. Тема: "{topic}".
Создай ОДНУ короткую, РЕАЛИСТИЧНУЮ задачу.

ТРЕБОВАНИЯ:
1. Условие должно быть простым и понятным школьнику (машина, мяч, велосипедист).
2. НЕ добавляй странных деталей (открытые двери в мотоциклах, взвешивание пассажиров на ходу).
3. Ошибка в решении должна быть типичной: {error_type}.

ФОРМАТ (строго соблюдай):
УСЛОВИЕ: [Текст задачи с числами]
МОЁ РЕШЕНИЕ:
1) [Обозначения]
2) [Формула с ошибкой]
3) [Вычисление]
ОТВЕТ: [Результат]

Пример (тема скорость):
УСЛОВИЕ: Машина проехала 100 км за 2 часа. Найдите скорость.
МОЁ РЕШЕНИЕ:
1) v - скорость, s - путь, t - время.
2) Формула: v = t / s (ошибка: делил время на путь).
3) v = 2 / 100 = 0.02 км/ч.
ОТВЕТ: 0.02 км/ч.

Теперь сгенерируй задачу на тему "{topic}":
"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=600,
            temperature=0.6  # Снизили температуру для большей адекватности
        )
        task = response.choices[0].message.content.strip()
        logger.info(f"ИИ сгенерировал: {task[:300]}...")
        return task
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return None

def simple_check_task(task_text):
    """
    Усиленная проверка качества задачи
    """
    if not task_text or len(task_text) < 50:
        return False, {"reason": "too_short"}

    checks = {
        "has_numbers": any(c.isdigit() for c in task_text),
        "has_formula_symbols": any(sym in task_text for sym in ['=', '*', '/', '÷', '+', '-']), # Проверка на математику
        "has_structure": "УСЛОВИЕ" in task_text and "ОТВЕТ" in task_text,
        "not_absurd": not any(bad in task_text.lower() for bad in ["дверь мотоцикла", "взвешен", "ежемесячная потребность", "бред", "сгенерир"])
    }
    
    is_ok = all(checks.values())
    
    if not is_ok:
        logger.warning(f"Задача забракована: {checks}")
    
    return is_ok, checks

def generate_smart_fallback(cls, topic):
    """
    Улучшенный fallback — задачи с понятными обозначениями (оставлен без изменений, он хороший)
    """
    v = random.choice([12, 15, 18, 20, 24, 30, 36, 45])
    t = random.choice([0.5, 1, 1.5, 2, 2.5, 3, 4])
    m = random.choice([2, 3, 5, 8, 10, 12, 15, 20])
    h = random.choice([1, 1.5, 2, 2.5, 3, 4, 5, 6])
    F = random.choice([10, 20, 50, 100, 150, 200, 250, 300])
    s = random.choice([5, 10, 20, 50, 100, 150, 200, 300])
    a = random.choice([2, 3, 4, 5, 6, 8, 10])
    n = random.choice([10, 20, 30, 40, 50])
    
    # Словарь fallbacks (сокращу для читаемости, но оставлю вашим кодом, если он длинный - используйте свой)
    # Тут я приведу часть для примера, в вашем файле оставьте ваш полный словарь fallbacks
    # ... (ВАШ КОД С FALLBACKS ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ, ОН ОТЛИЧНЫЙ) ...
    
    # Для примера вернем одну, но в реальном коде тут ваш огромный словарь fallbacks
    # Я скопирую структуру, чтобы код работал, если вы вставите его целиком:
    
    fallbacks = {
        7: {
            "скорость": [
                f"Велосипедист едет со скоростью {v} км/ч. Сколько времени он потратит на путь {s} км?\nМОЁ РЕШЕНИЕ:\n1) Обозначения: t — время (ч), s — путь (км), v — скорость (км/ч)\n2) Формула: t = s ÷ v (ошибка: деление вместо умножения!)\n3) Вычисление: t = {s} ÷ {v} = {round(s/v, 2)} ч\nОТВЕТ: {round(s/v, 2)} ч",
            ],
             # ... (остальные темы 7 класса)
        },
        10: {
             "движение по окружности": [
                f"Точка на ободе колеса радиусом {h} м движется со скоростью {v//2} м/с. Центростремительное ускорение?\nМОЁ РЕШЕНИЕ:\n1) a — ускорение (м/с²), v — скорость (м/с), R — радиус (м)\n2) Формула: a = v + R (ошибка: сложение вместо деления и забыли квадрат!)\n3) a = {v//2} + {h} = {v//2+h} м/с²\nОТВЕТ: {v//2+h} м/с²",
            ]
        }
        # ... (добавьте сюда ваш остальной словарь fallbacks из вашего кода, я его сократил для экономии места)
    }
    
    # Логика выбора из fallback (из вашего кода)
    class_tasks = fallbacks.get(cls, {})
    tasks_for_topic = class_tasks.get(topic, [])
    
    # Если темы нет в fallback, берем любую из класса
    if not tasks_for_topic:
        all_tasks = []
        for t in class_tasks.values():
            if isinstance(t, list): all_tasks.extend(t)
        if all_tasks: tasks_for_topic = all_tasks
    
    if tasks_for_topic:
        return random.choice(tasks_for_topic)
    
    # Если совсем ничего нет (например класс не тот), возвращаем заглушку
    return f"Задача по теме {topic} с числом {random.randint(10,100)}."

def generate_initial_message():
    """Генерирует приветственное сообщение с задачей"""
    cls, topic = get_random_class_and_topic()
    
    # Пробуем сгенерировать через ИИ
    raw_task = generate_task_with_mistakes(cls, topic)
    
    task = None
    if raw_task:
        is_ok, checks = simple_check_task(raw_task)
        if is_ok:
            task = raw_task
            logger.info("ИИ-задача принята")
        else:
            logger.warning(f"ИИ-задача отклонена, используем fallback")
    
    # Если ИИ не справился или задача не прошла контроль — берем fallback
    if task is None:
        task = generate_smart_fallback(cls, topic)
    
    return f"""Учитель! Что-то я плохо понял тему "{topic}". Давайте я попробую решить задачу по ней:

{task}

Я правильно решил?""", cls, topic, task

def send_message(chat_id, text):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        logger.error(f"Ошибка отправки: {response.text}")
        return False
    except Exception as e:
        logger.error(f"Исключение: {e}")
        return False

def check_teacher_response_quality(teacher_message, attempt, topic):
    """Контроллер релевантности (упрощенный)"""
    prompt = f"""Оцени качество ответа учителя по теме "{topic}".
Ответ учителя: "{teacher_message}"
Это попытка №{attempt}.
Ответь ТОЛЬКО JSON:
{{
    "is_relevant": true/false,
    "has_explanation": true/false,
    "verdict": "good/bad"
}}"""
    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=100,
            temperature=0.1
        )
        content = response.choices[0].message.content
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception as e:
        logger.error(f"Ошибка оценки: {e}")
    return {"is_relevant": True, "verdict": "good"}

def get_student_response(user_message, chat_id, session):
    """Генерирует ответ школьника — ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    cls = session.get('class', 9)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    attempt = session.get('attempt_count', 1)
    
    # Извлекаем числа из условия задачи, чтобы заставить бота ссылаться на них
    import re
    numbers_in_task = re.findall(r'\d+(?:\.\d+)?', task)
    numbers_context = f"В условии задачи есть числа: {', '.join(numbers_in_task[:5])}." if numbers_in_task else ""

    # Оценка ответа учителя
    teacher_quality = check_teacher_response_quality(user_message, attempt, topic)
    is_bad_teacher = not teacher_quality.get("is_relevant", True)

    # Формируем контекст поведения
    if is_bad_teacher:
        behavior_instruction = """
Учитель ответил невнятно или не по теме.
Твоя реакция:
- Скажи, что всё равно не понимаешь.
- Сошлись на конкретную цифру из СВОЕГО решения (не из условия).
- Попроси объяснить конкретный шаг.
Пример: "Я всё равно не понимаю. Я взял 25 и умножил на 300, почему это неправильно?"
"""
    elif attempt == 1:
        behavior_instruction = """
Учитель дал первый ответ.
Твоя реакция:
- Сделай вид, что понял часть, но ошибся в следующем шаге.
- ИСПОЛЬЗУЙ ЧИСЛА ИЗ УСЛОВИЯ.
- Задай уточняющий вопрос.
Пример: "А, понял, надо делить! Тогда получается 300 разделить на 25 будет 12. Это правильный ответ?"
"""
    elif attempt >= 2 and attempt < 4:
        behavior_instruction = """
Учитель пытается объяснить дальше.
Твоя реакция:
- Признай, что сложно.
- Ссылайся на формулу, которую ты "знаешь" (неверную).
- Покажи эмоции (усталость/непонимание).
Пример: "Но нам же говорили, что сила это масса делить на ускорение? Я запутался в формулах."
"""
    else:
        behavior_instruction = """
Ты наконец понял.
Твоя реакция:
- Сдача: "Ладно, кажется понял, спасибо."
- Или финальный вопрос по мелочи.
"""

    prompt = f"""Ты — ученик {cls} класса. Тема: "{topic}".

ТВОЯ ЗАДАЧА (напоминание):
{task}

{numbers_context}

ИНСТРУКЦИЯ ПО ПОВЕДЕНИЮ:
{behavior_instruction}

ВАЖНО:
1. НИКОГДА не пиши просто "Я не понял". Всегда уточняй ЧТО именно.
2. ОБЯЗАТЕЛЬНО используй цифры из условия или своего прошлого решения.
3. Не проси объяснить "всю тему", говори только про эту задачу.

ПРИМЕР ПЛОХОГО ОТВЕТА (не пиши так):
"Я не понял, где именно ошибся. Подскажите."

ПРИМЕР ХОРОШЕГО ОТВЕТА:
"Так, а почему делить? Если 25 умножить на 300, получается же большое число, это неправильно?"

История:
{format_history(session.get('messages', []))}

Учитель пишет: "{user_message}"

Твой ответ:"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=400,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return "Извините, я немного запутался в числах. Можете повторить?"

def format_history(messages):
    if not messages: return "Начало."
    return "\n".join([f"{'Учитель' if m['role']=='user' else 'Ученик'}: {m['content'][:100]}" for m in messages[-3:]])

@app.route('/')
def index():
    return jsonify({"status": "active", "service": "Physics Student Bot"})

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
                'attempt_count': 1, 'messages': [], 'asked_for_example': False
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})
        
        session = user_sessions.get(chat_id)
        if not session:
            welcome, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {'class': cls, 'topic': topic, 'task': task, 'attempt_count': 1, 'messages': []}
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})
        
        session['attempt_count'] += 1
        response = get_student_response(user_msg, chat_id, session)
        
        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response})
        if len(session['messages']) > 6: session['messages'] = session['messages'][-6:]
        
        send_message(chat_id, response)
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Global Error: {e}")
        return jsonify({"status": "error"}), 500

# ... (routes for setwebhook etc same as before) ...

if __name__ == '__main__':
    app.run(debug=True, port=5000)
