import logging
import sys
import time
from http import HTTPStatus
from os import getenv

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException
from telegram import Bot
from telegram.error import TelegramError

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

last_status = None


def setup_logging():
    """Настройка журналирования для бота."""
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(message)s',
        level=logging.DEBUG, stream=sys.stdout
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.ERROR)
    logging.getLogger(__name__).addHandler(handler)


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
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Отправка сообщения в Telegram: {message}')
    except TelegramError as error:
        logging.error(f'Ошибка при отправке сообщения в Telegram: {error}')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    try:
        params = {'from_date': timestamp}
        homework_statuses = requests.get(
            ENDPOINT, headers=HEADERS, params=params
        )
        if homework_statuses.status_code == HTTPStatus.OK:
            return homework_statuses.json()
        if homework_statuses.status_code == HTTPStatus.BAD_REQUEST:
            message = homework_statuses['error']['error']
        if homework_statuses.status_code == HTTPStatus.UNAUTHORIZED:
            message = homework_statuses['message']
        logging.error(message)
        send_message(bot, message)
    except RequestException as error:
        message = f'Ошибка при выполнении HTTP-запроса: {error}'
        logging.error(message)
        send_message(bot, message)


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        message = 'В ответе API структура данных не соответствует ожиданиям'
        logging.error(message)
        raise TypeError(message)
    elif 'homeworks' not in response:
        message = 'В ответe API отсутсвует ключ "homeworks"'
        logging.error(message)
        raise TypeError(message)
    elif not isinstance(response['homeworks'], list):
        message = ('В ответе API под ключом "homeworks" '
                   'данные приходят не в виде списка')
        logging.error(message)
        raise TypeError(message)
    return True


def parse_status(homework):
    """Извлекает из конкретной домашней работе статус этой работы."""
    for key in 'homework_name', 'status':
        if key not in homework:
            message = f'Ответ API не содержит ключа "{key}"'
            logging.error(message)
            raise KeyError(message)
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        message = ('Неожиданный статус домашней '
                   f'работы {homework_name}: {status}')
        logging.error(message)
        raise KeyError(message)
    verdict = HOMEWORK_VERDICTS[status]
    global last_status
    if last_status != status:
        last_status = status
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    setup_logging()
    check_tokens()

    global bot
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response['current_date']
            if check_response(response):
                homeworks = response['homeworks']
                for homework in homeworks:
                    send_message(bot, parse_status(homework))
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            send_message(bot, message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
