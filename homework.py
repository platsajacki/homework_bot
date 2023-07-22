import logging
import sys
import time
from http import HTTPStatus
from os import getenv

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException, HTTPError
from telegram import Bot
from telegram.error import TelegramError

from exceptions import ApiError

# Настройка журналирования для бота.
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO, stream=sys.stdout
)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.ERROR)
logging.getLogger(__name__).addHandler(handler)

load_dotenv()

PRACTICUM_TOKEN = getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    for token_name, token in tokens.items():
        if not token or token is None:
            message = f'{token_name} не найдет или пуст!'
            logging.critical(message)
            raise ValueError(message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    bot.send_message(TELEGRAM_CHAT_ID, message)
    logging.debug('Отправка сообщения в Telegram')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    try:
        params = {'from_date': timestamp}
        homework_statuses = requests.get(
            ENDPOINT, headers=HEADERS, params=params
        )
        if homework_statuses.status_code == HTTPStatus.OK:
            return homework_statuses.json()
        elif homework_statuses.status_code == HTTPStatus.BAD_REQUEST:
            raise HTTPError(homework_statuses.json()['error']['error'])
        elif homework_statuses.status_code == HTTPStatus.UNAUTHORIZED:
            raise HTTPError(homework_statuses.json()['message'])
        elif homework_statuses.status_code != HTTPStatus.OK:
            raise HTTPError('Произошла ошибка при выполнении запроса к API.')
    except RequestException as error:
        raise ApiError(error)


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            'В ответе API структура данных не соответствует ожиданиям'
        )
    elif (homeworks := response.get('homeworks')) is None:
        raise TypeError(
            'В ответe API отсутсвует ключ "homeworks"'
        )
    elif not isinstance(homeworks, list):
        raise TypeError(
            'В ответе API под ключом "homeworks" '
            'данные приходят не в виде списка'
        )


def parse_status(homework):
    """Извлекает из конкретной домашней работе статус этой работы."""
    for key in ['homework_name', 'status']:
        if key not in homework:
            raise KeyError(
                f'Ответ API не содержит ключа "{key}"'
            )
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(
            f'Неожиданный статус домашней работы {homework_name}: {status}'
        )
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            timestamp = response['current_date']
            homeworks = response['homeworks']
            if homeworks:
                if (message := parse_status(homeworks[0])) != last_message:
                    send_message(bot, message)
        except TelegramError as error:
            logging.error(f'Ошибка при отправке сообщения в Telegram: {error}')
        except Exception as error:
            message = f'Сбой в работе программы. {error}'
            logging.error(message)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
