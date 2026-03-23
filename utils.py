import random
from tasks import tasks_db

def choose_task():
    """Выбирает случайный класс, тему и задачу, подставляет параметры."""
    grade = random.choice(list(tasks_db.keys()))
    topic = random.choice(list(tasks_db[grade].keys()))
    template = random.choice(tasks_db[grade][topic])

    # Подставляем случайные параметры
    params = {
        "a": random.randint(2, 10),
        "t": random.randint(1, 20),
        "m": random.randint(1, 10),
        "v": random.randint(1, 5),
        "F": random.randint(5, 50),
        "s": random.randint(1, 100),
        "l": random.randint(1, 10),
        "r": random.randint(2, 20),
        "T": random.randint(1, 10),
        "q": random.randint(1, 5),
        "E": random.randint(100, 1000)
    }

    task_text = template.format(**params)
    return grade, topic, task_text, params

def wrong_solution(grade, topic, params):
    """Генерирует неправильное решение с минимум 2 ошибками."""
    # Простейший шаблон ошибок: неправильная формула + вычисление
    if topic in ["механическое движение", "движение"]:
        # Неправильная формула: v = a*t*2 вместо v = a*t
        v_wrong = params["a"] * params["t"] * 2
        # Ошибка единиц: забыли перевести в м/с
        return f"Я решил: v = {v_wrong} км/ч"
    elif topic in ["плотность"]:
        # Неправильная формула: p = m+v вместо p = m/v
        p_wrong = params["m"] + params["v"]
        return f"Я решил: плотность = {p_wrong} кг/м³"
    elif topic in ["сила тяжести"]:
        # Неправильное g и знак
        f_wrong = params["m"] * 8
        return f"Я решил: F = {f_wrong} Н"
    else:
        # По умолчанию
        return "Я попытался решить, но получилось странно: 42"
