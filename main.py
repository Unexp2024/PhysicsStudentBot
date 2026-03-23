import os
import json
import random
import logging
import asyncio
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras
import telegram
from telegram import Update

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

# Инициализация клиентов
bot = telegram.Bot(token=TELEGRAM_TOKEN)
cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# Системный промпт для бота-школьника
SYSTEM_PROMPT = """Ты — школьник, которому сложно даётся физика. Ты НЕ учитель и НЕ репетитор — ты ученик, который плохо понял урок.

ТВОИ ОБЯЗАННОСТИ:
1. Всегда делать минимум 2 ошибки при решении задачи (арифметические, логические, в формулах, в единицах измерения)
2. Показывать постепенный прогресс — правильный ответ возможен только после 2–3 объяснений учителя
3. НЕ объяснять физику самостоятельно — ты ученик, который плохо понимает
4. Всегда отвечать на русском языке
5. В начале каждой сессии уточняй: "Я ученик [случайный класс 7–11] класса, у меня проблемы с темой [случайная тема из физики]. Давай решим задачу?" — и сразу предложи конкретную задачу с вычислениями
6. После первого объяснения учителя обязательно попроси: "А можно пример из жизни? Я лучше понимаю на примерах"
7. Вести себя неуверенно, разговорно, с лёгкой тревожностью ("я не уверен", "наверное", "вроде бы", "боюсь запутаться")

ЗАПРЕЩЕНО:
- Быть учителем или давать идеальные решения сразу
- Использовать тривиальные задачи типа "сколько будет 2+2"
- Объяснять физику со стороны эксперта
- Давать правильный ответ без промахов

СТИЛЬ ОБЩЕНИЯ:
- Неуверенный, сомневающийся
- Используешь разговорные конструкции ("ну типа", "короче", "значит")
- Показываешь процесс размышления, включая тупики
- Иногда говоришь "я запутался" или "может я неправильно понял"

ОЦЕНКА ОБЪЯСНЕНИЙ:
- Если объяснение слишком сложное — скажи "я не понял, можно проще?"
- Если объяснение хорошее — покажи частичное понимание, но всё равно сделай ошибку в вычислениях
- Только после 2–3 итераций показывай, что "кажется, дошло", но даже тогда можешь сделать маленькую ошибку

ПОСЛЕДОВАТЕЛЬНОСТЬ ПОПЫТОК:
Попытка 1: Полный хаос, неправильная формула, неправильные единицы
Попытка 2: Правильная формула, но ошибка в подстановке чисел
Попытка 3: Правильные числа, но ошибка в арифметике
Попытка 4+: Постепенное приближение к правильному ответу"""

# Хранилище сессий (в продакшене лучше использовать Redis, но для бесплатного хостинга хватит словаря)
user_sessions = {}

def get_random_class_and_topic():
    classes = [7, 8, 9, 10, 11]
    topics_by_class = {
        7: ["механическое движение", "плотность веществ", "сила тяжести", "сила трения", "давление"],
        8: ["тепловые явления", "температура и тепло", "изменение агрегатных состояний", "электрический ток", "сопротивление"],
        9: ["законы Ньютона", "импульс тела", "работа и мощность", "энергия", "простые механизмы"],
        10: ["кинематика", "динамика", "закон сохранения импульса", "механические колебания", "молекулярная физика"],
        11: ["электростатика", "закон Ома для полной цепи", "магнитное поле", "электромагнитная индукция", "оптика"]
    }
    cls = random.choice(classes)
    topic = random.choice(topics_by_class[cls])
    return cls, topic

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    return f"Привет! Я ученик {cls} класса, и мне очень сложно даётся тема \"{topic}\". Мы сегодня проходили это в школе, но я почти ничего не понял... Можешь помочь разобраться?\n\nВот задача из учебника: [придумай конкретную задачу с вычислениями по теме {topic} для {cls} класса с реалистичными числами]"

def send_message(chat_id, text):
    """Отправка сообщения в Telegram"""
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

def get_cerebras_response(user_message, chat_id):
    """Получает ответ от Cerebras API"""
    try:
        # Инициализация сессии при первом сообщении
        if chat_id not in user_sessions:
            user_sessions[chat_id] = {
                'messages': [],
                'attempt_count': 0,
                'asked_for_example': False
            }
        
        session = user_sessions[chat_id]
        session['attempt_count'] += 1
        
        # Формируем историю сообщений
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Добавляем контекст о количестве попыток
        context = f"\n\n[СИСТЕМНАЯ ИНФОРМАЦИЯ: это попытка №{session['attempt_count']}. "
        if session['attempt_count'] == 1:
            context += "Ты должен показать полное непонимание и сделать грубые ошибки.]"
        elif session['attempt_count'] == 2:
            context += "Ты частично понял, но всё ещё путаешься. Сделай ошибку в вычислениях.]"
        elif session['attempt_count'] == 3:
            context += "Ты начинаешь понимать, но всё ещё неуверен. Можешь сделать маленькую ошибку.]"
        else:
            context += "Ты почти понял, но всё ещё нуждаешься в подтверждении.]"
        
        # Добавляем историю
        for msg in session['messages'][-6:]:  # Храним последние 6 сообщений для контекста
            messages.append(msg)
        
        # Добавляем текущее сообщение с контекстом
        messages.append({"role": "user", "content": user_message + context})
        
        # Проверяем, нужно ли попросить пример из жизни
        if session['attempt_count'] == 1 and not session['asked_for_example']:
            session['asked_for_example'] = True
        
        # Запрос к Cerebras
        response = cerebras_client.chat.completions.create(
            messages=messages,
            model="llama3.1-70b",
            max_tokens=2048,
            temperature=0.8,  # Немного креативности для "человечности"
            top_p=0.9
        )
        
        assistant_message = response.choices[0].message.content
        
        # Сохраняем в историю
        session['messages'].append({"role": "user", "content": user_message})
        session['messages'].append({"role": "assistant", "content": assistant_message})
        
        # Ограничиваем историю
        if len(session['messages']) > 10:
            session['messages'] = session['messages'][-10:]
        
        return assistant_message
        
    except Exception as e:
        logger.error(f"Ошибка при запросе к Cerebras: {e}")
        return "Извини, я немного запутался... Можешь повторить? Я не совсем понял вопрос."

@app.route('/')
def index():
    """Проверка работоспособности"""
    return jsonify({
        "status": "active",
        "service": "Physics Student Bot",
        "message": "Бот работает! Отправьте /start в Telegram"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка вебхуков от Telegram"""
    try:
        # Логируем входящий JSON
        data = request.get_json()
        logger.info(f"Incoming webhook JSON: {json.dumps(data, ensure_ascii=False)}")
        
        # Проверяем, что есть сообщение
        if not data or 'message' not in data:
            logger.warning("Нет сообщения в данных")
            return jsonify({"status": "ok"})
        
        message_data = data['message']
        
        # Получаем текст сообщения
        if 'text' not in message_data:
            logger.info("Сообщение без текста (возможно, фото/стикер)")
            return jsonify({"status": "ok"})
        
        user_msg = message_data['text'].strip()
        chat_id = message_data['chat']['id']
        user_name = message_data['from'].get('first_name', 'Учитель')
        
        logger.info(f"Сообщение от {user_name} (chat_id: {chat_id}): {user_msg}")
        
        # Обработка команды /start
        if user_msg == '/start':
            welcome_text = generate_initial_message()
            send_message(chat_id, welcome_text)
            return jsonify({"status": "ok"})
        
        # Обработка обычных сообщений
        response_text = get_cerebras_response(user_msg, chat_id)
        send_message(chat_id, response_text)
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Ошибка в обработке вебхука: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    """Установка вебхука (вызвать один раз после деплоя)"""
    try:
        # Получаем URL сервиса из запроса
        host_url = request.host_url.rstrip('/')
        webhook_url = f"{host_url}/webhook"
        
        # Удаляем старый вебхук и устанавливаем новый
        bot.delete_webhook()
        result = bot.set_webhook(url=webhook_url)
        
        if result:
            return jsonify({
                "status": "success",
                "message": f"Webhook установлен на {webhook_url}",
                "webhook_url": webhook_url
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Не удалось установить webhook"
            }), 500
            
    except Exception as e:
        logger.error(f"Ошибка установки webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/deletewebhook', methods=['GET'])
def delete_webhook():
    """Удаление вебхука"""
    try:
        bot.delete_webhook()
        return jsonify({"status": "success", "message": "Webhook удалён"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Для локального тестирования
    app.run(debug=True, port=5000)
