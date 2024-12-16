import random
import re
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Global state for HiLo games
hilo_limit = {}

deck = []
number = ['A','2','3','4','5','6','7','8','9','10','J','Q','K']
suit = ['♦️','♥️','♣️','♠️']
for i in number:
    for j in suit:
        deck.append(f'{j}{i}')

# Helper functions
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def dump(user_data, user_id):
    users_collection.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)

# HiLo Command
async def HiLo(update, context):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    data = get_user_by_id(user_id)
    
    if not data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return
    
    credit = data["credits"]
    cd = context.user_data

    if user_id not in hilo_limit:
        hilo_limit[user_id] = 0

    if hilo_limit[user_id] >= 15:
        await update.message.reply_text('Daily limit of 15 games reached\nAny query, can ask <code>@Unban_shit</code>', parse_mode=ParseMode.HTML)
        return

    try:
        bet = int(update.message.text.split()[1])
        if bet < 100:
            await update.message.reply_text('Minimum Bet is 100 👾')
            return

        if bet > 10000:
            await update.message.reply_text('Maximum bet is 10,000 👾')
            return

        if credit < bet:
            await update.message.reply_text('Not enough credit to make this bet')
            return

        data["credits"] -= bet
        dump(data, user_id)
    except:
        await update.message.reply_text('/HiLo <bet amount>')
        return

    # Ensure proper emoji handling by removing unnecessary variation selectors
    hand = random.choice(deck)
    table = random.choice(deck)

    # Replace problematic emoji with safer equivalents if needed
    hand = hand.replace('♥️', '♥')  # Just an example to remove variation selector

    text = f'<b><u>\ud83d\udd3c HiLo Game \ud83d\udd3d</u></b>\n\n'
    text += f'Bet amount : {bet} \ud83d\udc7e\n'
    text += f'Current multiplier : None\n\n'
    text += f'You have : <b>{hand}</b>\n'
    text += f'On Table : <b>?</b>\n\n'
    text += f'<i>How to play: Choose High if you predict the card on table is higher value than your card,</i>\n'
    text += f'<i>Choose Low if you predict the card on table is lower value than your card.</i>\n'
    text += f'<i>You can cashout anytime, but losing 1 guess and its game over, you lose all balances.</i>'

    message = await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    message_id = message.message_id

    cd[message_id] = {"bet": bet, "keyboard": keyboard, "logs": [f'|{hand}'], "user_id": user_id, "hand": hand, "table": table, "mult": 1}



# HiLo Click Handler
def HiLo_click(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    cd = context.user_data
    message_id = query.message.message_id
    data = cd[message_id]

    if user_id != data['user_id']:
        query.answer('Not yours', show_alert=True)
        return None

    hand = data['hand']
    table = data['table']
    mult = data['mult']
    bet = data['bet']

    # Value Mapping
    mapping = {k: v for v, k in enumerate(['A','2','3','4','5','6','7','8','9','10','J','Q','K'])}
    p_mapping = {i: 1.062 + abs(6 - i) * 0.1 for i in range(13)}

    user_number = mapping[re.search(r'[A-Z0-9]+$', hand).group()]
    table_number = mapping[re.search(r'[A-Z0-9]+$', table).group()]

    choice = query.data.split("_")[-1]
    logs = data['logs']
    logs.append(f'|{table}')
    if len(logs) > 5:
        logs.pop(0)
    log_text = ''.join(logs)

    if (choice == 'High' and user_number <= table_number) or (choice == 'Low' and user_number >= table_number):
        multiplier = p_mapping[user_number]
        text = f'<b><u>\ud83d\udd3c HiLo Game \ud83d\udd3d</u></b>\n\n'
        text += f'Bet amount : {bet} \ud83d\udc7e\n'
        text += f'Current multiplier : {round(multiplier * mult, 3)}x\n'
        text += f'Winning Amount : {int(bet * multiplier * mult)}\ud83d\udc7e\n\n'
        text += f'Card on Table revealed to be {table}, You bet on {choice} and won!\n<b>Now guess the next one!</b>\n\n'
        text += f'You have : <b>{table}</b>\nOn Table : <b>?</b>\n\n'
        text += f'<b><u>Logs</u></b>\n{log_text}'

        cd[message_id].update({"hand": table, "table": random.choice(deck), "mult": multiplier * mult})
        query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(data['keyboard']), parse_mode=ParseMode.HTML)
    else:
        hilo_limit[user_id] += 1
        query.edit_message_text(
            f'<b><u>\ud83d\udd3c HiLo Game \ud83d\udd3d</u></b>\n\nBet amount: {bet} \ud83d\udc7e\nCurrent multiplier: 0x\n\nCard on Table revealed to be {table}, You bet on {choice} and Lost!\n<b>Game Over</b>\n\n<b><u>Logs</u></b>\n{log_text}',
            parse_mode=ParseMode.HTML)
# CashOut Handler
def Hilo_CashOut(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    cd = context.user_data
    message_id = query.message.message_id
    data = cd[message_id]

    if user_id != data['user_id']:
        query.answer('Not yours', show_alert=True)
        return None

    hilo_limit[user_id] += 1
    winnings = int(data['bet'] * data['mult'])
    user_data = get_user_by_id(user_id)
    user_data['credits'] += winnings
    save_user(user_data)

    # Format the cash-out message similar to the example provided
    game_message = (
        "<b><u>\ud83d\udd3c HiLo Game \ud83d\udd3d</u></b>\n\n"
        f"Bet amount: {data['bet']} \ud83d\udc7e\n"
        f"Current multiplier: {round(data['mult'], 3)}x\n\n"
        "🎰 *Game Over*\n\n"
        "► You decided to [Take] your winnings.\n"
        f"► You won: {winnings} 👾\n"
        f"► Total Credits: {user_data['credits']} 👾\n\n"
        "<b><u>Logs</u></b>\n"
        ''.join(data['logs'])
    )

    query.edit_message_text(game_message, parse_mode=ParseMode.HTML)

