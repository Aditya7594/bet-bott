import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient
from telegram.constants import ParseMode

# MongoDB client to store user data
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
users_collection = db['users']

# Function to get user data from MongoDB
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": str(user_id)})

# Function to save user data to MongoDB
def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Global dictionary for tracking current Mines games
current_mines_games = {}

# Command to start Mines game
async def Mines(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user_by_id(user_id)
    
    # Check if the user already has an active game
    if any(game for game in current_mines_games.values() if game['user_id'] == user_id):
        await update.message.reply_text("You already have an ongoing game! Please finish your current game first.")
        return
    
    if not user_data:
        await update.message.reply_text("No user data found. Please try again later.")
        return

    credit = user_data.get("credits", 0)  # Get user's credits

    # Parse bet amount and number of bombs from the command
    bet = 0
    total_bombs = 0
    try:
        bet = int(update.message.text.split()[1])
        total_bombs = int(update.message.text.split()[2])

        if bet < 100:
            await update.message.reply_text('Minimum Bet is 100 👾')
            return

        if bet > 10000:
            await update.message.reply_text('Maximum bet is 10,000 👾')
            return

        if total_bombs < 1 or total_bombs > 25:
            await update.message.reply_text('You can only have between 1 and 25 bombs.')
            return

        if credit < bet:
            await update.message.reply_text('Not enough credits to place this bet.')
            return

        user_data["credits"] -= bet
        save_user(user_data)

    except Exception as e:
        await update.message.reply_text('/Mines <bet amount> <bomb count>')
        return

    # Generate a grid of size 5x5
    grid_size = 5
    grid = [["" for _ in range(grid_size)] for _ in range(grid_size)]
    bomb_positions = random.sample(range(grid_size * grid_size), total_bombs)
    for bomb in bomb_positions:
        row, col = divmod(bomb, grid_size)
        grid[row][col] = "💣"

    # Generate a unique game ID
    game_id = str(random.randint(100000, 999999))
    
    # Set up the game state with bet and bomb values
    game_state = {
        'game_id': game_id,
        'bet': bet,
        'grid': grid,
        'revealed': set(),
        'mines': bomb_positions,
        'user_id': user_id,
        'multiplier': 1,
        'mines_hit': False,
        'total_bombs': total_bombs,
        'in_progress': True,
        'players': {user_id: {'name': update.effective_user.first_name, 'credits': bet}}
    }

    current_mines_games[game_id] = game_state

    # Set up the buttons
    keyboard = []
    for row in range(grid_size):
        keyboard.append([InlineKeyboardButton("❓", callback_data=f"mines_{game_id}_{row * grid_size + col}") for col in range(grid_size)])

    keyboard.append([InlineKeyboardButton('CashOut', callback_data=f"mines_cashout_{game_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"<b><u>💎 Mines Game 💎</u></b>\n\n"
    text += f"Game ID: {game_id}\n"
    text += f"Bet amount: {bet} 👾\n"
    text += f"Current multiplier: {game_state['multiplier']}x\n"
    text += f"Safe tiles: {grid_size * grid_size - total_bombs}\n\n"
    text += f"<i>Click on tiles to reveal and avoid bombs! You can CashOut anytime!</i>"

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def Mines_click(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id, position = query.data.split('_')
    position = int(position)
    game_state = current_mines_games.get(game_id)

    if not game_state or not game_state.get('in_progress', False):
        await query.answer("No active game found. Start a new game with /Mines <bet_amount> <bomb_count>.", show_alert=True)
        return

    if user_id != game_state['user_id']:
        await query.answer("This is not your game!", show_alert=True)
        return

    bet = game_state['bet']
    grid = game_state['grid']
    revealed = game_state['revealed']
    mines_hit = game_state['mines_hit']
    row, col = divmod(position, 5)

    # If the user has already revealed this tile, ignore the click
    if (row, col) in revealed:
        await query.answer("You've already revealed this tile.", show_alert=True)
        return

    revealed.add((row, col))

    # If the player hits a mine, game over
    if grid[row][col] == "💣":
        game_state['mines_hit'] = True
        # Reveal all bombs
        for r in range(5):
            for c in range(5):
                if grid[r][c] == "💣":
                    grid[r][c] = "💣"  # Show all bombs

        text = f"<b><u>💎 Mines Game 💎</u></b>\n\n"
        text += f"Game ID: {game_id}\n"
        text += f"Bet amount: {bet} 👾\n"
        text += f"Current multiplier: {game_state['multiplier']}x\n"
        text += f"<b>You hit a bomb! Game Over!</b>\n"
        text += f"Total amount lost: {bet} 👾"

        # Notify the user about the game over and refund the credits
        user_data = get_user_by_id(user_id)
        user_data["credits"] += bet
        save_user(user_data)

        # End the game session and update in-progress status
        game_state['in_progress'] = False
        del current_mines_games[game_id]

        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return

    # Reveal the tile
    grid[row][col] = "💎"  # Safe tile revealed

    # Calculate multiplier based on the number of safe tiles revealed
    revealed_tiles = len(revealed)
    safe_tiles = (5 * 5) - len(game_state['mines'])  # Total safe tiles
    multiplier = 1 + (revealed_tiles / safe_tiles)  # Start at 1 and increase with more safe tiles

    # Update the game state
    game_state['multiplier'] = round(multiplier, 2)

    # Prepare the grid display
    keyboard = []
    for i in range(5):
        keyboard.append([InlineKeyboardButton(grid[i][j] if (i, j) in revealed else "❓", callback_data=f"mines_{game_id}_{i * 5 + j}") for j in range(5)])

    keyboard.append([InlineKeyboardButton('CashOut', callback_data=f"mines_cashout_{game_id}")])

    # Update game info and send it
    text = f"<b><u>💎 Mines Game 💎</u></b>\n\n"
    text += f"Game ID: {game_id}\n"
    text += f"Bet amount: {bet} 👾\n"
    text += f"Current multiplier: {game_state['multiplier']}x\n"
    text += f"Safe tiles remaining: {(5 * 5) - len(revealed) - len(game_state['mines'])}\n"
    text += f"<i>Click on tiles to reveal and avoid bombs! CashOut anytime!</i>"

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

# Handle CashOut button
async def Mines_CashOut(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = update.effective_user.id
    _, game_id = query.data.split('_')
    game_state = current_mines_games.get(game_id)

    if not game_state or not game_state.get('in_progress', False):
        await query.answer("No active game found. Start a new game with /Mines <bet_amount> <bomb_count>.", show_alert=True)
        return

    if user_id != game_state['user_id']:
        await query.answer("This is not your game!", show_alert=True)
        return

    bet = game_state['bet']
    multiplier = game_state['multiplier']
    winnings = int(bet * multiplier)

    user_data = get_user_by_id(user_id)
    if not user_data:
        user_data = {"user_id": user_id, "credits": 0}
        save_user(user_data)

    # Add winnings to the user's credits
    user_data["credits"] += winnings
    save_user(user_data)

    # End the game session and update in-progress status
    game_state['in_progress'] = False
    del current_mines_games[game_id]

    text = f"<b><u>💎 Mines Game 💎</u></b>\n\n"
    text += f"Game ID: {game_id}\n"
    text += f"Bet amount: {bet} 👾\n"
    text += f"Current multiplier: {game_state['multiplier']}x\n"
    text += f"<b>You cashed out and won: {winnings} 👾</b>"

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)

def get_mines_handlers():
    """Return all Mines game handlers."""
    return [
        CommandHandler("Mines", Mines),
        CallbackQueryHandler(Mines_click, pattern="^mines_"),
        CallbackQueryHandler(Mines_CashOut, pattern="^mines_cashout_")
    ]
