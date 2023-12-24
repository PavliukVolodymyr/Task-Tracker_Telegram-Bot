import datetime
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
        # Успішна авторизація, обробити токени, ID користувача та відповідні дії
        access_token = response.get('access_token', '')
        refresh_token = response.get('refresh_token', '')
        user_id = response.get('ID', '')  # Додайте новий ключ для ID користувача
        save_tokens_to_database(chat_id, access_token, refresh_token, user_id)
        bot.send_message(chat_id, f"Успішна авторизація!")


def save_tokens_to_database(chat_id, access_token, refresh_token, user_id):
    access_token1, refresh_token1, user_id1, seen_tasks = get_tokens_from_database(chat_id)
    # Підключення до бази даних
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Збереження токенів та ID користувача у таблиці
    cursor.execute('''
        INSERT OR REPLACE INTO tokens (chat_id, access_token, refresh_token, user_id, seen_tasks)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, access_token, refresh_token, user_id, seen_tasks))

    # Збереження змін у базі даних
    conn.commit()

    # Закриття підключення до бази даних
    conn.close()

# Функція для отримання токенів користувача з бази даних
def get_tokens_from_database(chat_id):
    try:
        # Підключення до бази даних
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        # Отримання токенів з таблиці за chat_id
        cursor.execute('SELECT access_token, refresh_token, user_id, seen_tasks FROM tokens WHERE chat_id=?', (chat_id,))
        result = cursor.fetchone()

        # Закриття підключення до бази даних
        conn.close()

        if result:
            access_token, refresh_token, user_id, seen_tasks = result
            return access_token, refresh_token, user_id, seen_tasks
    except sqlite3.Error as e:
        print(f"SQLite error: {str(e)}")

    return None, None, None


@bot.message_handler(commands=['tasks'])
def get_user_tasks(message):
    # Отримання ідентифікатора чату
    chat_id = message.chat.id

    # Отримання токенів користувача з бази даних
    access_token, refresh_token, user_id, seen_tasks = get_tokens_from_database(chat_id)

    if access_token:
        # Виклик функції для отримання завдань з API
        tasks = get_user_tasks_from_api(access_token)

        # Відправка завдань користувачу
        if tasks:
            bot.send_message(chat_id, "Ваші завдання:")
            for task in tasks:
                if not task.get('completed', False):
                    task_name = task.get('title', 'Невідома назва')
                    task_description = task.get('description', '')
                    # Перевірка, чи опис не має значення "Task description (optional)"
                    if task_description != 'Task description (optional)':
                        # Якщо опис не має значення "Task description (optional)", включити його у текстове представлення завдання
                        task_description_text = f"\nОпис: {task_description}"
                    else:
                        task_description_text = ''

                    task_due_date = task.get('due_date', 'Без терміну виконання')

                    # Створення текстового представлення завдання для відправлення
                    task_text = f"Назва: {task_name}{task_description_text}\nТермін виконання: {task_due_date}"

                    # Відправлення текстового представлення завдання
                    bot.send_message(chat_id, task_text)
        else:
            bot.send_message(chat_id, "У вас немає завдань.")
    else:
        bot.send_message(chat_id, "Ви не авторизовані. Введіть /start та авторизуйтеся.")

# Функція для отримання завдань користувача з API
def get_user_tasks_from_api(access_token):
    api_url = f'https://vaabr5.pythonanywhere.com/api/tracker/projects/boards/lists/tasks/assigned/'
    headers = {'Authorization': f'Bearer {access_token}'}

    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            tasks = response.json()
            return tasks
        else:
            print(f"Failed to fetch tasks. Status code: {response.status_code}")
    except requests.RequestException as e:
        print(f"Error fetching tasks: {str(e)}")

    return None

def update_seen_tasks(chat_id, last_seen_task_id):
    try:
        # Підключення до бази даних
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        # Оновлення колонки 'seen_tasks' для конкретного чату
        cursor.execute('UPDATE tokens SET seen_tasks=? WHERE chat_id=?', (last_seen_task_id, chat_id))

        # Збереження змін у базі даних
        conn.commit()

        # Закриття підключення до бази даних
        conn.close()
    except sqlite3.Error as e:
        print(f"SQLite error: {str(e)}")
        
@bot.message_handler(commands=['new'])
def get_new_user_tasks(message):
    # Отримання ідентифікатора чату
    chat_id = message.chat.id

    # Отримання токенів користувача з бази даних
    access_token, refresh_token, user_id, last_seen_task_id = get_tokens_from_database(chat_id)

    if access_token:
        # Виклик функції для отримання всіх завдань з API
        all_tasks = get_user_tasks_from_api(access_token)

        # Виклик функції для отримання завдань, які користувач ще не бачив
        unseen_tasks = get_unseen_tasks(all_tasks, last_seen_task_id)

        # Відправка завдань користувачу
        if unseen_tasks:
            bot.send_message(chat_id, "Нові завдання, які ви ще не бачили:")
            for task in unseen_tasks:
                task_name = task.get('title', 'Невідома назва')
                task_description = task.get('description', '')

                # Перевірка, чи опис не має значення "Task description (optional)"
                if task_description != 'Task description (optional)':
                    # Якщо опис не має значення "Task description (optional)", включити його у текстове представлення завдання
                    task_description_text = f"\nОпис: {task_description}"
                else:
                    task_description_text = ''

                task_due_date = task.get('due_date', 'Без терміну виконання')

                # Створення текстового представлення завдання для відправлення
                task_text = f"Назва: {task_name}{task_description_text}\nТермін виконання: {task_due_date}"

                # Відправлення текстового представлення завдання
                bot.send_message(chat_id, task_text)

            # Оновлення бази даних інформацією про останнє завдання, яке користувач вже бачив
            last_seen_task_id = str(all_tasks[-1]['id'])
            update_seen_tasks(chat_id, last_seen_task_id)
        else:
            bot.send_message(chat_id, "У вас немає нових завдань.")
    else:
        bot.send_message(chat_id, "Ви не авторизовані. Введіть /start та авторизуйтеся.")

def get_unseen_tasks(all_tasks, last_seen_task_id):
    unseen_tasks = []

    # Перевірка, чи є останнє id завдання
    if last_seen_task_id:
        last_seen_task_id = int(last_seen_task_id)
    else:
        last_seen_task_id = 0
        
        # Фільтрація завдань, які мають більший id, ніж останнє бачене
        unseen_tasks = [task for task in all_tasks if task['id'] > last_seen_task_id]

    return unseen_tasks


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
