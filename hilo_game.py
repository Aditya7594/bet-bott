import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
from pymongo import MongoClient

client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Function to get user data from MongoDB
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": str(user_id)})

# Function to save user data to MongoDB
def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Sample deck for HiLo game
deck = []
number = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
suit = ['♦️', '♥️', '♣️', '♠️']
for i in number:
    for j in suit:
        deck.append(f'{j}{i}')

# Global game state
cd = {}  # Context data for each game
hilo_limit = {}  # Tracks the number of games played by each user

# Start command to initialize HiLo game
async def HiLo(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user_by_id(user_id)
    credit = user_data.get("credits", 0)  # Fix to get the user's credits
    user_name = update.effective_user.first_name
    query = update.callback_query
    keyboard = [[]]

    if user_id not in hilo_limit:
        hilo_limit[user_id] = 0

    if hilo_limit[user_id] >= 15:
        await update.message.reply_text('Daily limit of 15 games reached', parse_mode=ParseMode.HTML)
        return

    bet = 0
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

        user_data["credits"] -= bet
        save_user(user_data)  # Deduct bet from the user's credits

    except:
        await update.message.reply_text('/HiLo <bet amount>')
        return

    keyboard.append([InlineKeyboardButton('High', callback_data='Hilo_High'), InlineKeyboardButton('Low', callback_data='Hilo_Low')])
    keyboard.append([InlineKeyboardButton('CashOut', callback_data='HiLoCashOut')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    hand = random.choice(deck)
    table = random.choice(deck)

    text = f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
    text += f'Bet amount: {bet} 👾\n'
    text += f'Current multiplier: None\n\n'
    text += f'You have: <b>{hand}</b>\n'
    text += f'On Table: <b>?</b>\n\n'
    text += f'<i>How to play: Choose High if you predict the card on table is higher value than your card,</i>\n'
    text += f'<i>Choose Low if you predict the card on table is lower value than your card.</i>\n'
    text += f'<i>You can cashout anytime, but losing 1 guess and its game over, you lose all balances.</i>'

    message = await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    message_id = message.message_id

    # Store game data using message_id to track the session
    cd[message_id] = {
        'bet': bet,
        'keyboard': keyboard,
        'logs': [f'|{hand}'],
        'user_id': user_id,
        'hand': hand,
        'table': table,
        'mult': 1
    }

async def HiLo_click(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    message_id = query.message.message_id

    if message_id not in cd:
        await query.answer("No active game found. Start a new game with /HiLo <bet_amount>.", show_alert=True)
        return

    game_data = cd[message_id]
    player_id = game_data['user_id']

    if user_id != player_id:
        await query.answer("This game is not yours.", show_alert=True)
        return

    logs = game_data['logs']
    bet = game_data['bet']
    hand = game_data['hand']
    table = game_data['table']
    mult = game_data['mult']
    keyboard = game_data['keyboard']

    mapping = {'A': 0, '2': 1, '3': 2, '4': 3, '5': 4, '6': 5, '7': 6, '8': 7, '9': 8, '10': 9, 'J': 10, 'Q': 11, 'K': 12}
    p_mapping = {0: 1.062, 1: 1.158, 2: 1.274, 3: 1.416, 4: 1.593, 5: 1.82, 6: 2.123, 7: 1.82, 8: 1.593, 9: 1.416, 10: 1.274, 11: 1.158, 12: 1.062}

    user_card = re.search(r'[A-Z0-9]+$', hand).group()
    table_card = re.search(r'[A-Z0-9]+$', table).group()
    user_number = mapping[user_card]
    table_number = mapping[table_card]

    choice = query.data.split("_")[-1]
    logs.append(f'|{table}')
    if len(logs) > 5:
        logs.pop(0)

    log_text = ''.join(logs)

    if (choice == 'High' and user_number <= table_number) or (choice == 'Low' and user_number >= table_number):
        multiplier = p_mapping[user_number]
        winnings = int(bet * multiplier * mult)

        # Update session data instead of directly adding credits
        cd[message_id]['hand'] = table
        cd[message_id]['table'] = random.choice(deck)
        cd[message_id]['mult'] = multiplier * mult
        cd[message_id]['winnings'] = winnings  # Store winnings for cashout

        text = (
            f"<b><u>📈 HiLo Game 📉</u></b>\n\n"
            f"Bet amount: {bet} 👾\n"
            f"Current multiplier: {round(multiplier * mult, 3)}x\n"
            f"Potential Winnings: {winnings} 👾\n\n"
            f"Card on Table revealed to be {table}. You bet on {choice} and won!\n<b>Now guess the next one!</b>\n\n"
            f"You have: <b>{table}</b>\nOn Table: <b>?</b>\n\n"
            f"<b><u>Logs</u></b>\n{log_text}"
        )

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    else:
        text = (
            f"<b><u>📈 HiLo Game 📉</u></b>\n\n"
            f"Bet amount: {bet} 👾\n"
            f"Current multiplier: {0}x\n\n"
            f"Card on Table revealed to be {table}. You bet on {choice} and lost!\n<b>Game Over</b>\n\n"
            f"<b><u>Logs</u></b>\n{log_text}"
        )
        hilo_limit[user_id] += 1
        del cd[message_id]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)



async def HiLo_CashOut(update: Update, context: CallbackContext):
    query = update.callback_query
    message_id = query.message.message_id
    user_id = update.effective_user.id

    if message_id not in cd:
        await query.answer("Game session has expired or doesn't exist.", show_alert=True)
        return

    game_data = cd[message_id]
    bet = game_data['bet']
    mult = game_data['mult']
    winnings = game_data.get('winnings', 0)  # Get stored winnings
    logs = game_data['logs']
    player_id = game_data['user_id']

    if user_id != player_id:
        await query.answer("This game session is not yours!", show_alert=True)
        return

    user_data = get_user_by_id(user_id)
    if not user_data:
        user_data = {"user_id": user_id, "credits": 0}
        save_user(user_data)

    # Add the winnings to the user's credits
    user_data['credits'] += winnings
    save_user(user_data)

    del cd[message_id]
    hilo_limit[user_id] += 1

    log_text = ''.join(logs)
    text = (
        f'<b><u>📈 HiLo Game 📉</u></b>\n\n'
        f'Bet amount: {bet} 👾\n'
        f'Final multiplier: {round(mult, 3)}x\n'
        f'<b>You Won: {winnings} 👾</b>\n\n'
        f'<b><u>Logs</u></b>\n{log_text}'
    )

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)

