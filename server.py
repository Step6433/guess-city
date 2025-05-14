from flask import Flask, request, jsonify
import logging
import random

# Создаем экземпляр Flask-приложения
app = Flask(__name__)

# Настройка уровня логирования
logging.basicConfig(level=logging.INFO)

# Карта городов и изображений
cities = {
    'Москва': ['1652229/acb6960206f22c4eea7c', '1540737/44047c5b619159102c69'],
    'Нью-Йорк': ['1540737/8d702285aceb6a8d2c11', '1030494/c9b7244c325bbf45e763'],
    'Париж': ['1030494/864cde96c659c976ab0d', '1540737/44a3b9adbd45a69ef158']
}

# Словарь сессий пользователей
session_storage = {}

# Координаты городов
city_coordinates = {
    'Москва': '55.751244,37.618423',
    'Нью-Йорк': '40.712776,-74.005974',
    'Париж': '48.856614,2.352222'
}


@app.route('/post', methods=['POST'])
def main():
    """
    Основная точка входа для обработки вебхука от Яндекс.Алисы.
    """
    logging.info('Request: %r', request.json)

    # Формируем базовую структуру ответа
    response = {
        'session': request.json['session'],
        'version': request.json['version'],
        'response': {
            'end_session': False,
            'buttons': [{'title': 'Помощь', 'hide': True}]  # добавляем кнопку помощи
        }
    }

    try:
        # Обрабатываем диалог между пользователем и Алисой
        handle_dialog(response, request.json)

        # Возвращаем сформированный ответ в формате JSON
        logging.info('Response: %r', response)
        return jsonify(response)
    except Exception as e:
        logging.error('Error processing request: %s', str(e))
        return jsonify({'error': 'Internal server error'}), 500


def handle_dialog(res, req):
    """
    Основной обработчик диалога.
    """
    user_id = req['session']['user_id']

    # Начало новой сессии
    if req['session']['new']:
        res['response']['text'] = 'Привет! Назови свое имя!'
        session_storage[user_id] = {
            'first_name': None,  # Имя пользователя
            'game_started': False,  # Флаг начала игры
            'guessed_cities': [],  # Список отгаданных городов
            'current_city': None,  # Текущий загаданный город
            'guess_country': False  # Флаг проверки страны
        }
        return

    # Проверяем нажатие кнопки "помощь"
    if 'Помощь' in req['request']['original_utterance']:
        show_help_message(res)
        return

    # Получение имени пользователя
    if session_storage[user_id].get('first_name') is None:
        first_name = get_first_name(req)
        if first_name is None:
            res['response']['text'] = 'Не расслышала имя. Повтори, пожалуйста!'
        else:
            session_storage[user_id]['first_name'] = first_name
            session_storage[user_id]['guessed_cities'] = []

            # Предложение начать игру
            res['response']['text'] = f'Привет, {first_name.title()}! Давай попробуем угадать город по фотографии?'
            res['response']['buttons'] += [
                {'title': 'Да', 'hide': True},
                {'title': 'Нет', 'hide': True}
            ]
    else:
        # Пользователь согласился играть?
        if not session_storage[user_id]['game_started']:
            if 'да' in req['request']['nlu']['tokens']:
                # Начинаем игру
                session_storage[user_id]['game_started'] = True

                # Выбираем город для игры
                available_cities = list(set(cities.keys()) - set(session_storage[user_id]['guessed_cities']))
                current_city = random.choice(available_cities)
                session_storage[user_id]['current_city'] = current_city

                # Показываем первую фотографию
                res['response']['card'] = {
                    'type': 'BigImage',
                    'title': 'Отгадай город!',
                    'image_id': cities[current_city][0],
                }
                res['response']['text'] = 'Давай посмотрим первое фото.'
            elif 'нет' in req['request']['nlu']['tokens']:
                res['response']['text'] = 'Жаль! Может позже...'
                res['end_session'] = True
            else:
                res['response']['text'] = 'Не поняла тебя... Ты хочешь поиграть или нет?'
                res['response']['buttons'] += [
                    {'title': 'Да', 'hide': True},
                    {'title': 'Нет', 'hide': True}
                ]
        else:
            # Игра уже началась
            current_city = session_storage[user_id]['current_city']
            guessed_city = get_city(req)

            if guessed_city.lower() == current_city.lower():  # Правильный ответ!
                country = get_country_for_city(current_city)
                session_storage[user_id]['guess_country'] = True

                # Предлагаем угадать страну
                res['response'][
                    'text'] = f'Верно! Это действительно {current_city}. А теперь назови страну, в которой находится этот город!'
            elif session_storage[user_id]['guess_country']:
                # Игрок пытается угадать страну
                guessed_country = get_country(req)
                if guessed_country.lower() == country.lower():
                    res['response'][
                        'text'] = f'Правильно! Город {current_city} находится в стране {country}. Попробуем еще раз?'
                    session_storage[user_id]['guessed_cities'].append(current_city)
                    session_storage[user_id]['game_started'] = False
                    session_storage[user_id]['guess_country'] = False

                    # Генерация ссылки на карту
                    city_coords = city_coordinates[current_city]
                    map_url = f'https://yandex.ru/maps/?mode=search&text={current_city}&ll={city_coords}'
                    res['response']['buttons'] += [
                        {'title': 'Показать город на карте', 'url': map_url, 'hide': True}
                    ]
                else:
                    res['response']['text'] = f'Упс, неверная страна. Подумайте ещё!'
            else:
                next_photo_idx = len([x for x in session_storage[user_id]['guessed_cities'] if x != current_city])
                if next_photo_idx >= len(cities[current_city]):
                    # Все фотографии показаны, сообщаем ответ
                    res['response']['text'] = f'Ой, увы, это была {current_city}. Попробуем снова?'
                    session_storage[user_id]['guessed_cities'].append(current_city)
                    session_storage[user_id]['game_started'] = False
                else:
                    # Пытаемся показать следующее фото
                    res['response']['card'] = {
                        'type': 'BigImage',
                        'title': 'Подсказка:',
                        'image_id': cities[current_city][next_photo_idx],
                    }
                    res['response']['text'] = 'Еще одна подсказка...'


def get_country_for_city(city):
    """Возвращает страну для заданного города."""
    countries = {
        'Москва': 'Россия',
        'Нью-Йорк': 'США',
        'Париж': 'Франция'
    }
    return countries.get(city, '')


def get_country(req):
    """Получаем название страны из запроса."""
    for entity in req['request']['nlu']['entities']:
        if entity['type'] == 'YANDEX.GEO':
            return entity['value'].get('country')
    return None


def get_city(req):
    """Получаем название города из запроса."""
    for entity in req['request']['nlu']['entities']:
        if entity['type'] == 'YANDEX.GEO':
            return entity['value'].get('city')
    return None


def get_first_name(req):
    """Получаем имя пользователя из запроса."""
    for entity in req['request']['nlu']['entities']:
        if entity['type'] == 'YANDEX.FIO':
            return entity['value'].get('first_name')
    return None


def show_help_message(res):
    """Показываем сообщение с инструкциями"""
    help_text = (
        'Это простая игра, где нужно угадать загаданный мной город'
        'по фотографиям достопримечательностей.\n\n'
        '- Нажми **«Да»**, чтобы начать игру.\n'
        '- Чтобы завершить игру, напиши **«нет»**.'
    )
    res['response']['text'] = help_text


if __name__ == '__main__':
    app.run()