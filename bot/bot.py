import telebot
from telebot import types
import concurrent.futures
from flask import Flask, request, jsonify
import requests
import sqlite3

bot_token = '6553192435:AAH79hmvkIbfz3Wj2uS3rk8ppsKRt_BqgO8'
bot = telebot.TeleBot(bot_token)

DJANGO_BACKEND_URL = 'https://vaabr5.pythonanywhere.com/api/user/login/'

app = Flask(__name__)

# Додаткові змінні для зберігання імені користувача та паролю
username_storage = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    # Створення inline клавіатури з кнопкою "Авторизація"
    markup = types.InlineKeyboardMarkup()
    item = types.InlineKeyboardButton("Авторизація", callback_data='auth_button')
    markup.add(item)

    # Відправлення повідомлення з inline клавіатурою
    bot.send_message(message.chat.id, "Привіт! Я твій телеграм-бот для отримання завдань з Task trecker. Для початку треба авторизуватися", reply_markup=markup)

# Обробник для натискання inline кнопки "Авторизація"
@bot.callback_query_handler(func=lambda call: call.data == 'auth_button')
def handle_auth_button(call):
    # Відправлення повідомлення з проханням ввести ім'я користувача
    bot.send_message(call.message.chat.id, "Введіть своє ім'я користувача для авторизації:")
    bot.register_next_step_handler(call.message, process_username_input)

def process_username_input(message):
    # Збереження ім'я користувача для подальшого використання при авторизації
    chat_id = message.chat.id
    username = message.text
    username_storage[chat_id] = username

    # Відправлення повідомлення з проханням ввести пароль
    bot.send_message(chat_id, "Введіть свій пароль для авторизації:")
    bot.register_next_step_handler(message, process_password_input)

def process_password_input(message):
    # Отримання імені користувача зі збережених даних
    chat_id = message.chat.id
    username = username_storage.get(chat_id)

    if username:
        # Отримання паролю та виклик функції для обробки авторизації
        password = message.text
        handle_auth(chat_id, username, password)
    else:
        bot.send_message(chat_id, "Помилка. Спробуйте ще раз.")

def handle_auth(chat_id, username, password):
    # Тут ви можете використовувати ім'я користувача та пароль для авторизації
    # Наприклад, відправити їх на ваш Django бекенд і обробити відповідь
    data = {'username': username, 'password': password}
    try:
        response = requests.post(DJANGO_BACKEND_URL, json=data)
        if response.status_code == 200:
            # Якщо авторизація успішна, обробити відповідь
            handle_auth_response(chat_id, response.json())
        else:
            bot.send_message(chat_id, "Помилка авторизації. Спробуйте ще раз.")
    except requests.RequestException as e:
        bot.send_message(chat_id, f"Помилка авторизації: {str(e)}")

def handle_auth_response(chat_id, response):
    if 'error' in response:
        # Виникла помилка при авторизації
        bot.send_message(chat_id, f"Помилка авторизації: {response['error']}")
    else:
        # Успішна авторизація, обробити токени та відповідні дії
        access_token = response.get('access_token', '')
        refresh_token = response.get('refresh_token', '')
        save_tokens_to_database(chat_id, access_token, refresh_token)
        bot.send_message(chat_id, f"Успішна авторизація!")

def save_tokens_to_database(chat_id, access_token, refresh_token):
    # Підключення до бази даних
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Збереження токенів у таблиці
    cursor.execute('''
        INSERT OR REPLACE INTO tokens (chat_id, access_token, refresh_token)
        VALUES (?, ?, ?)
    ''', (chat_id, access_token, refresh_token))

    # Збереження змін у базі даних
    conn.commit()

    # Закриття підключення до бази даних
    conn.close()

# Flask-роут для обробки вхідних HTTP-запитів від Телеграм
@app.route(f'/{bot_token}', methods=['POST'])
def telegram_webhook():
    json_string = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_string)

    # Передача update до функції обробки нових повідомлень бота
    bot.process_new_updates([update])
    return jsonify({'status': 'ok'})

# Функція для запуску Flask додатка
def run_flask():
    app.run(port=8443, debug=False)

# Функція для запуску бота
def run_telegram_bot():
    bot.polling(none_stop=True)

# Запускаємо функції одночасно
with concurrent.futures.ThreadPoolExecutor() as executor:
    executor.submit(run_flask)
    executor.submit(run_telegram_bot)
