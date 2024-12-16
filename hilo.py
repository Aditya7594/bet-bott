import random
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

# Initialize the deck of cards
deck = []
number = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
suit = ['♦️', '♥️', '♣️', '♠️']
for i in number:
    for j in suit:
        deck.append(f'{j}{i}')

# Dictionary to keep track of daily limits
hilo_limit = {}

# HiLo Command (starting the game)
def HiLo(update, context):
    data = get_data()
    user_id = update.effective_user.id
    credit = data["users"][str(user_id)]["credits"]
    cd = context.user_data
    user_name = update.effective_user.first_name
    query = update.callback_query
    keyboard = [[]]

    if user_id not in hilo_limit:
        hilo_limit[user_id] = 0

    if hilo_limit[user_id] >= 15:
        update.message.reply_text('Daily limit of 15 games reached\nAny query, can ask <code>@Unban_shit</code>', parse_mode=ParseMode.HTML)
        return

    bet = 0
    try:
        bet = int(update.message.text.split()[1])
        if bet < 100:
            update.message.reply_text('Minimum Bet is 100 👾')
            return

        if bet > 10000:
            update.message.reply_text('Maximum bet is 10,000 👾')
            return

        if credit < bet:
            update.message.reply_text('Not enough credit to make this bet')
            return

        data["users"][str(user_id)]["credits"] -= bet
        dump(data["users"][str(user_id)], user_id)

    except:
        update.message.reply_text('/HiLo <bet amount>')
        return

    keyboard.append([InlineKeyboardButton('High', callback_data='Hilo_High'), InlineKeyboardButton('Low', callback_data='Hilo_Low')])
    keyboard.append([]) 
    keyboard[-1].append(InlineKeyboardButton('CashOut', callback_data='HiLoCashOut'))

    reply_markup = InlineKeyboardMarkup(keyboard)

    hand = random.choice(deck)
    table = random.choice(deck)

    text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
    text += f'Bet amount : {bet} 👾\n'
    text += f'Current multiplier : None\n\n'
    text += f'You have : <b>{hand}</b>\n'
    text += f'On Table : <b>?</b>\n\n'
    text += f'<i>How to play: Choose High if you predict the card on the table is higher value than your card,</i>\n'
    text += f'<i>Choose Low if you predict the card on the table is lower value than your card.</i>\n'
    text += f'<i>You can cashout anytime, but losing 1 guess and it\'s game over, you lose all balances.</i>'

    message = update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    message_id = message.message_id

    cd[message_id] = {}
    cd[message_id]['bet'] = bet
    cd[message_id]['keyboard'] = keyboard
    cd[message_id]['logs'] = [f'|{hand}']
    cd[message_id]['user_id'] = user_id
    cd[message_id]['hand'] = hand
    cd[message_id]['table'] = table
    cd[message_id]['mult'] = 1

# HiLo Click Handler (user clicks on High/Low)
def HiLo_click(update, context):
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    cd = context.user_data
    query = update.callback_query
    message_id = query.message.message_id
    keyboard = cd[message_id]['keyboard']
    logs = cd[message_id]['logs']
    bet = cd[message_id]['bet']
    player_id = cd[message_id]['user_id']
    hand = cd[message_id]['hand']
    table = cd[message_id]['table']
    mult = cd[message_id]['mult']

    if update.callback_query.from_user.id != player_id:
        query.answer('Not yours', show_alert=True)
        return None

    house_edge = 0.98

    mapping = {
        'A': 0,
        '2': 1,
        '3': 2,
        '4': 3,
        '5': 4,
        '6': 5,
        '7': 6,
        '8': 7,
        '9': 8,
        '10': 9,
        'J': 10,
        'Q': 11,
        'K': 12,
    }

    p_mapping = {
        0: 1.062,
        1: 1.158,
        2: 1.274,
        3: 1.416,
        4: 1.593,
        5: 1.82,
        6: 2.123,
        7: 1.82,
        8: 1.593,
        9: 1.416,
        10: 1.274,
        11: 1.158,
        12: 1.062,
    }

    match = re.search(r'[A-Z0-9]+$', hand)
    user_card = match.group()
    match = re.search(r'[A-Z0-9]+$', table)
    table_card = match.group()
    user_number = mapping.get(user_card)
    table_number = mapping.get(table_card)

    choice = query.data.split("_")[-1]
    logs.append(f'|{table}')
    if len(logs) > 5:
        logs.remove(logs[0])

    log_text = ''
    for i in logs:
        log_text += i

    if choice == 'High':
        if user_number <= table_number:
            multiplier = p_mapping.get(user_number)

            text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
            text += f'Bet amount : {bet} 👾\n'
            text += f'Current multiplier : {round(multiplier * mult, 3)}x\n'
            text += f'Winning Amount : {int(bet * multiplier * mult)}👾\n\n'
            text += f'Card on Table revealed to be {table}, You bet on High and won!\n<b>Now guess the next one!</b>\n\n'
            text += f'You have : <b>{table}</b>\n'
            text += f'On Table : <b>?</b>\n\n'
            text += f'<b><u>Logs</u></b>\n{log_text}'

            cd[message_id]['hand'] = table
            cd[message_id]['table'] = random.choice(deck)
            cd[message_id]['mult'] = multiplier * mult
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

        if user_number > table_number:
            text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
            text += f'Bet amount : {bet} 👾\n'
            text += f'Current multiplier : {0}x\n\n'
            text += f'<b><u>Logs</u></b>\n{log_text}\n\n'
            text += f'Card on Table revealed to be {table}, You bet on High and Lost!\n<b>Game Over</b>\n'
            hilo_limit[user_id] += 1
            query.edit_message_text(text, parse_mode=ParseMode.HTML)

    if choice == 'Low':
        if user_number >= table_number:
            multiplier = p_mapping.get(user_number)

            text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
            text += f'Bet amount : {bet} 👾\n'
            text += f'Current multiplier : {round(multiplier * mult, 3)}x\n'
            text += f'Winning Amount : {int(bet * multiplier * mult)}👾\n\n'
            text += f'Card on Table revealed to be {table}, You bet on Low and won!\n<b>Now guess the next one!</b>\n\n'
            text += f'You have : <b>{table}</b>\n'
            text += f'On Table : <b>?</b>\n\n'
            text += f'<b><u>Logs</u></b>\n{log_text}'

            cd[message_id]['hand'] = table
            cd[message_id]['table'] = random.choice(deck)
            cd[message_id]['mult'] = multiplier * mult
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

        if user_number < table_number:
            text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
            text += f'Bet amount : {bet} 👾\n'
            text += f'Current multiplier : {0}x\n\n'
            text += f'<b><u>Logs</u></b>\n{log_text}\n\n'
            text += f'Card on Table revealed to be {table}, You bet on Low and Lost!\n<b>Game Over</b>\n'
            hilo_limit[user_id] += 1
            query.edit_message_text(text, parse_mode=ParseMode.HTML)

# HiLo CashOut Handler (user decides to cash out)
def Hilo_CashOut(update, context):
    data = get_data()
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    cd = context.user_data
    query = update.callback_query
    message_id = query.message.message_id
    keyboard = cd[message_id]['keyboard']
    logs = cd[message_id]['logs']
    bet = cd[message_id]['bet']
    player_id = cd[message_id]['user_id']
    hand = cd[message_id]['hand']
    table = cd[message_id]['table']
    mult = cd[message_id]['mult']

    log_text = ''
    for i in logs:
        log_text += i

    if update.callback_query.from_user.id != player_id:
        query.answer('Not yours', show_alert=True)
        return None

    winning_amount = int(bet * mult)

    data["users"][str(user_id)]["credits"] += winning_amount
    dump(data["users"][str(user_id)], user_id)

    text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
    text += f'Bet amount : {bet} 👾\n'
    text += f'Winning Amount : {winning_amount} 👾\n'
    text += f'You cashed out and won {winning_amount} 👾!\n\n'
    text += f'<b><u>Logs</u></b>\n{log_text}'
    query.edit_message_text(text, parse_mode=ParseMode.HTML)
