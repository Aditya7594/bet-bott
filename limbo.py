import random
import uuid
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
users_collection = db['users']
limbo_games_collection = db['limbo_games']  # Separate MongoDB collection for Limbo games

# Weighted multiplier generation thresholds for Limbo
MULTIPLIER_THRESHOLDS = [
    (0.5, 0.8),   # 50% chance for multipliers between 0.5 - 0.8
    (0.81, 1.5),  # 30% chance for multipliers between 0.81 - 1.5
    (1.51, 2.5),  # 15% chance for multipliers between 1.51 - 2.5
    (2.51, 4.0),  # 5% chance for multipliers between 2.51 - 4.0
]

# MongoDB functions
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Limbo Game functions
def generate_weighted_multiplier():
    random_number = random.uniform(0, 1)
    if random_number <= 0.1:
        return 0  # 10% chance to lose everything instantly
    elif random_number <= 0.7:
        return round(random.uniform(0.5, 1.0), 2)  # Increased lower bound
    elif random_number <= 0.9:
        return round(random.uniform(1.1, 1.5), 2)  # Increased range
    elif random_number <= 0.98:
        return round(random.uniform(1.6, 2.2), 2)  # Increased range
    else:
        return round(random.uniform(2.3, 3.0), 2)  # Increased upper bound

async def limbo(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Get bet amount
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide a valid bet amount. Example: /limbo 1000")
        return

    bet_amount = int(context.args[0])

    # Enforce maximum bet limit
    if bet_amount > 30000:
        await update.message.reply_text("Maximum bet for Limbo is 30,000 credits.")
        return

    # Check credits
    if user_data['credits'] < bet_amount:
        await update.message.reply_text("You don't have enough credits to play.")
        return

    # Deduct bet and initialize game
    user_data['credits'] -= bet_amount
    save_user(user_data)

    # Generate random multipliers
    multipliers = [generate_weighted_multiplier() for _ in range(5)]

    # Generate a unique game ID
    game_id = str(uuid.uuid4())

    # Store the game in the MongoDB collection for Limbo games
    limbo_games_collection.insert_one({
        'user_id': user_id,
        'game_id': game_id,
        'bet': bet_amount,
        'multipliers': multipliers,
        'current_index': 0
    })

    await send_limbo_message(update, user_id, context, game_id)

# Function to send Limbo game message
async def send_limbo_message(update: Update, user_id: str, context: CallbackContext, game_id: str):
    limbo_game = limbo_games_collection.find_one({"user_id": user_id, "game_id": game_id})
    if not limbo_game:
        return

    current_index = limbo_game['current_index']
    bet = limbo_game['bet']
    current_multiplier = limbo_game['multipliers'][current_index]

    # Generate inline buttons
    keyboard = []
    if current_index < 4:
        keyboard.append([
            InlineKeyboardButton("Take", callback_data=f"take_{user_id}_{game_id}"),
            InlineKeyboardButton("Next", callback_data=f"next_{user_id}_{game_id}")
        ])
    else:
        keyboard.append([InlineKeyboardButton("Take", callback_data=f"take_{user_id}_{game_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    multipliers_display = '\n'.join([f"{i+1}. {'?' if i > current_index else limbo_game['multipliers'][i]}" for i in range(5)])

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
        await update.message.reply_text(game_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(game_message, reply_markup=reply_markup, parse_mode='Markdown')

# Handle Limbo button presses (Take or Next)
async def handle_limbo_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data.split('_')
    action = data[0]
    user_id = data[1]
    game_id = data[2]

    limbo_game = limbo_games_collection.find_one({"user_id": user_id, "game_id": game_id})
    if not limbo_game:
        await query.edit_message_text("No active game found. Start a new game with /limbo <bet_amount>.")
        return

    if action == 'take':
        await handle_take(update, context, user_id, game_id)
    elif action == 'next':
        await handle_next(update, context, user_id, game_id)

# Handle Take action
async def handle_take(update: Update, context: CallbackContext, user_id: str, game_id: str):
    limbo_game = limbo_games_collection.find_one_and_delete({"user_id": user_id, "game_id": game_id})
    if not limbo_game:
        return

    multiplier = limbo_game['multipliers'][limbo_game['current_index']]
    winnings = int(limbo_game['bet'] * multiplier)

    # Update user's credits
    user_data = get_user_by_id(user_id)
    user_data['credits'] += winnings
    save_user(user_data)

    await update.callback_query.edit_message_text(
        f"🚀 You took the multiplier *{multiplier}x* and won *{winnings} credits*! 🎉",
        parse_mode='Markdown'
    )

# Handle Next action (moving to next multiplier)
async def handle_next(update: Update, context: CallbackContext, user_id: str, game_id: str):
    limbo_game = limbo_games_collection.find_one({"user_id": user_id, "game_id": game_id})
    if not limbo_game:
        return

    if limbo_game['current_index'] < 4:
        new_index = limbo_game['current_index'] + 1
        limbo_games_collection.update_one(
            {"user_id": user_id, "game_id": game_id},
            {"$set": {"current_index": new_index}}
        )
        
        # Get the current message text
        current_text = update.callback_query.message.text
        
        # Generate new message text
        multipliers_display = '\n'.join([f"{i+1}. {'?' if i > new_index else limbo_game['multipliers'][i]}" for i in range(5)])
        new_text = (
            "🎰 *Limbo Game*:\n\n"
            "► If you are happy with the current multiplier, you can [Take] it.\n"
            "► If you see the next multiplier, you won't be able to go back.\n"
            "► System will auto [Take] when you reach the last multiplier box.\n\n"
            f"{multipliers_display}\n\n"
            f"*Bet Amount*: {limbo_game['bet']} 👾\n"
            f"*Current Multiplier*: {limbo_game['multipliers'][new_index]}x"
        )
        
        # Only edit if the text has changed
        if current_text != new_text:
            await send_limbo_message(update, user_id, context, game_id)
    else:
        await handle_take(update, context, user_id, game_id)