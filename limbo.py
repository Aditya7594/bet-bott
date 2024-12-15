import random
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Global game state
current_limbo_games = {}

def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

async def limbo(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    user_data = get_user_by_id(user_id)

    # Check if user started the bot
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Get bet amount
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide a valid bet amount. Example: /limbo 1000")
        return
    bet_amount = int(context.args[0])

    # Check credits
    if user_data['credits'] < bet_amount:
        await update.message.reply_text("You don't have enough credits to play.")
        return

    # Deduct bet and initialize game
    user_data['credits'] -= bet_amount
    save_user(user_data)

    multipliers = [round(random.uniform(0.0, 4.0), 2) for _ in range(5)]
    current_limbo_games[user_id] = {
        'bet': bet_amount,
        'multipliers': multipliers,
        'current_index': 0,
    }

    await send_limbo_message(update, user_id, context)

async def send_limbo_message(update: Update, user_id: str, context: CallbackContext):
    game = current_limbo_games.get(user_id)
    if not game:
        return

    current_index = game['current_index']
    bet = game['bet']
    current_multiplier = game['multipliers'][current_index]

    # Generate inline buttons
    keyboard = [
        [InlineKeyboardButton("Take", callback_data=f"take_{user_id}"),
         InlineKeyboardButton("Next", callback_data=f"next_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    multipliers_display = '\n'.join([
        f"{i+1}. {'?' if i > current_index else game['multipliers'][i]}"
        for i in range(5)
    ])

    game_message = (
        "🎰 *Limbo Game*:\n\n"
        "► If you are happy with the current multiplier, you can [Take] it.\n"
        "► If you see the next multiplier, you won't be able to go back.\n"
        "► System will auto [Take] when you reach the last multiplier box.\n\n"
        f"{multipliers_display}\n\n"
        f"*Bet Amount*: {bet} 👾\n"
        f"*Current Multiplier*: {current_multiplier}x"
    )

    if update.message:
        sent_message = await update.message.reply_text(
            game_message, reply_markup=reply_markup, parse_mode='Markdown'
        )
    else:
        chat_id = update.callback_query.message.chat_id
        sent_message = await context.bot.send_message(
            chat_id=chat_id, text=game_message, reply_markup=reply_markup, parse_mode='Markdown'
        )

    context.user_data['limbo_message_id'] = sent_message.message_id

async def handle_limbo_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    game = current_limbo_games.get(user_id)
    if not game:
        await query.edit_message_text("No active game found. Start a new game with /limbo <bet_amount>.")
        return

    action = query.data.split('_')[0]
    if action == 'take':
        await handle_take(update, context, user_id)
    elif action == 'next':
        await handle_next(update, context, user_id)

async def handle_take(update: Update, context: CallbackContext, user_id: str):
    game = current_limbo_games.pop(user_id, None)
    if not game:
        return

    multiplier = game['multipliers'][game['current_index']]
    winnings = int(game['bet'] * multiplier)

    # Update credits
    user_data = get_user_by_id(user_id)
    user_data['credits'] += winnings
    save_user(user_data)

    await update.callback_query.edit_message_text(
        f"\ud83d\ude80 You took the multiplier *{multiplier}x* and won *{winnings} credits*! \ud83c\udf89",
        parse_mode='Markdown'
    )

async def handle_next(update: Update, context: CallbackContext, user_id: str):
    game = current_limbo_games.get(user_id)
    if not game:
        return

    if game['current_index'] < 4:
        game['current_index'] += 1
        await send_limbo_message(update, user_id, context)
    else:
        await handle_take(update, context, user_id)
