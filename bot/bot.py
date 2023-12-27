import datetime
import telebot
from telebot import types
import concurrent.futures
from flask import Flask, request, jsonify
import requests
import sqlite3
import schedule
import time

bot_token = '6553192435:AAH79hmvkIbfz3Wj2uS3rk8ppsKRt_BqgO8'
bot = telebot.TeleBot(bot_token)

DJANGO_BACKEND_URL = 'https://vaabr5.pythonanywhere.com/api/user/login/'

app = Flask(__name__)

# Додаткові змінні для зберігання імені користувача та паролю
username_storage = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Створення inline клавіатури з кнопкою "Авторизація"
    markup = types.InlineKeyboardMarkup()
    item = types.InlineKeyboardButton("Авторизація", callback_data='auth_button')
    markup.add(item)

    # Відправлення повідомлення з inline клавіатурою
    bot.send_message(message.chat.id, "Привіт! Я твій телеграм-бот для отримання завдань з Task tracker. Для початку треба авторизуватися", reply_markup=markup)

@bot.message_handler(commands=['help'])
def show_help(message):
    help_text = (
        "Доступні команди:\n"
        "/start - початок використання бота та авторизація\n"
        "/tasks - перегляд ваших завдань\n"
        "/new - перегляд нових завдань\n"
        "/help - вивід цього повідомлення"
    )
    bot.send_message(message.chat.id, help_text)

def logout_user(chat_id):
    try:
        # Підключення до бази даних
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        # Видалення токенів користувача з бази даних
        cursor.execute('DELETE FROM tokens WHERE chat_id=?', (chat_id,))
        conn.commit()

        # Закриття підключення до бази даних
        conn.close()

    except sqlite3.Error as e:
        print(f"SQLite error: {str(e)}")

@bot.message_handler(commands=['logout'])
def handle_logout(message):
    chat_id = message.chat.id

    # Виклик функції для виходу користувача
    logout_user(chat_id)

    # Відправлення повідомлення про вихід
    bot.send_message(chat_id, "Ви вийшли з системи. Введіть /start для повторної авторизації.")

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
    try:
        # Підключення до бази даних
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        # Перевірка, чи існує запис з вказаним chat_id
        cursor.execute('SELECT * FROM tokens WHERE chat_id=?', (chat_id,))
        existing_record = cursor.fetchone()

        if existing_record:
            # Виконання UPDATE
            cursor.execute('''
                UPDATE tokens 
                SET access_token=?, refresh_token=?, user_id=?
                WHERE chat_id=?
            ''', (access_token, refresh_token, user_id, chat_id))
        else:
            # Виконання INSERT, оскільки запис відсутній
            cursor.execute('''
                INSERT INTO tokens (chat_id, access_token, refresh_token, user_id)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, access_token, refresh_token, user_id))

        # Збереження змін у базі даних
        conn.commit()
    except sqlite3.Error as e:
        print(f"SQLite error: {str(e)}")
    finally:
        # Закриття підключення до бази даних навіть у випадку винятку
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
    refresh_tokens(chat_id)

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
    refresh_tokens(chat_id)

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

def send_periodic_notifications():
    try:
        # Підключення до бази даних
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor() 

        # Отримання усіх користувачів з токенами з бази даних
        cursor.execute('SELECT chat_id FROM tokens WHERE access_token IS NOT NULL')
        users_with_tokens = cursor.fetchall()

        # Отримання усіх завдань для кожного користувача
        for user in users_with_tokens:
            chat_id = user[0]
            refresh_tokens(chat_id)
            access_token, _, _, last_seen_task_id = get_tokens_from_database(chat_id)
            all_tasks = get_user_tasks_from_api(access_token)

            # Отримання нових завдань, які користувач ще не бачив
            unseen_tasks = get_unseen_tasks(all_tasks, last_seen_task_id)

            if unseen_tasks:
                bot.send_message(chat_id, "Нові завдання, які ви ще не бачили:")
                for task in unseen_tasks:
                    task_name = task.get('title', 'Невідома назва')
                    task_description = task.get('description', '')
                    if task_description != 'Task description (optional)':
                        task_description_text = f"\nОпис: {task_description}"
                    else:
                        task_description_text = ''
                    task_due_date = task.get('due_date', 'Без терміну виконання')
                    task_text = f"Назва: {task_name}{task_description_text}\nТермін виконання: {task_due_date}"
                    bot.send_message(chat_id, task_text)

                # Оновлення бази даних інформацією про останнє завдання, яке користувач вже бачив
                last_seen_task_id = str(all_tasks[-1]['id'])
                update_seen_tasks(chat_id, last_seen_task_id)

        # Закриття підключення до бази даних
        conn.close()
    except Exception as e:
        print(f"Error in send_periodic_notifications: {str(e)}")
        
def refresh_tokens(chat_id):
    refresh_url = 'https://vaabr5.pythonanywhere.com/api/user/token/refresh/'
    _,refresh_token,user_id,_ =get_tokens_from_database(chat_id)
    data = {'refresh_token': refresh_token}
    try:
        response = requests.post(refresh_url, json=data)
        if response.status_code == 200:
            new_tokens = response.json()
            access_token = new_tokens.get('access', '')
            save_tokens_to_database(chat_id, access_token, refresh_token, user_id)
            return access_token
        else:
            print(f"Failed to refresh tokens. Status code: {response.status_code}")
    except requests.RequestException as e:
        print(f"Error refreshing tokens: {str(e)}")

    return None



    

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

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Реєстрація функції в розкладі на виклик кожні 5 хвилин
schedule.every(30).seconds.do(send_periodic_notifications)
        
# Запускаємо функції одночасно
with concurrent.futures.ThreadPoolExecutor() as executor:
    executor.submit(run_flask)
    executor.submit(run_telegram_bot)
    executor.submit(run_schedule)