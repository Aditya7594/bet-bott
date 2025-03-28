import os
import random
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient
from datetime import datetime

# MongoDB setup (unchanged)
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Game Configuration
CARD_VALUES = {'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13}
SUITS = ['diamonds', 'hearts', 'clubs', 'spades']
DECK = [(suit, value) for suit in SUITS for value in CARD_VALUES.keys()]

# Enhanced Game State Management
class HiLoGameManager:
    def __init__(self):
        self.games = {}
        self.daily_limits = {}
        self.max_daily_games = 10
        self.min_bet = 100
        self.max_bet = 10000
        self.base_multiplier = 1.0
        self.multiplier_increment = 0.5
        self.max_multiplier = 5.0

    def get_user(self, user_id):
        user = users_collection.find_one({"user_id": str(user_id)})
        if not user:
            user = {"user_id": str(user_id), "credits": 1000}
            users_collection.insert_one(user)
        return user

    def update_user(self, user_id, credits):
        users_collection.update_one({"user_id": str(user_id)}, {"$set": {"credits": credits}}, upsert=True)

    def can_play_game(self, user_id):
        if user_id not in self.daily_limits:
            self.daily_limits[user_id] = 0
        return self.daily_limits[user_id] < self.max_daily_games

    def start_game(self, user_id, bet):
        player_card = random.choice(DECK)
        self.games[user_id] = {
            "bet": bet,
            "player_card": player_card,
            "multiplier": self.base_multiplier,
            "rounds_played": 0
        }
        return player_card

    def process_guess(self, user_id, guess):
        game = self.games.get(user_id)
        if not game:
            return None, None, None

        player_card = game["player_card"]
        table_card = random.choice(DECK)
        
        player_value = CARD_VALUES[player_card[1]]
        table_value = CARD_VALUES[table_card[1]]

        # Determine if guess is correct
        is_correct = (guess == "high" and table_value > player_value) or \
                     (guess == "low" and table_value < player_value)

        if is_correct:
            # Increase multiplier with diminishing returns
            game["multiplier"] = min(
                self.base_multiplier + (game["rounds_played"] * self.multiplier_increment), 
                self.max_multiplier
            )
            game["player_card"] = table_card
            game["rounds_played"] += 1
        
        return is_correct, table_card, game["multiplier"]

    def calculate_winnings(self, user_id):
        game = self.games.get(user_id)
        if not game:
            return 0
        
        winnings = round(game["bet"] * game["multiplier"])
        del self.games[user_id]
        self.daily_limits[user_id] += 1
        return winnings

# Resize card image function (unchanged)
def resize_card_image(card):
    suit, value = card
    folder_path = os.path.join(os.path.dirname(__file__), "playingcards")
    filename = f"{suit.lower()}_{value}.png"
    path = os.path.join(folder_path, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Card image not found: {path}")

    resized_path = os.path.join(folder_path, f"resized_{suit.lower()}_{value}.png")
    if not os.path.exists(resized_path):
        with Image.open(path) as img:
            img.thumbnail((200, 300))  # Resize to smaller dimensions
            img.save(resized_path)
    return resized_path

# Initialize game manager
game_manager = HiLoGameManager()

# Start HiLo game
async def start_hilo(update: Update, context):
    """Start a new HiLo game."""
    user_id = str(update.effective_user.id)
    user_data = game_manager.get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return
        
    # Check for bet amount in command
    bet_amount = 0
    if context.args:
        try:
            bet_amount = int(context.args[0])
            if bet_amount < 0:
                await update.message.reply_text("Bet amount cannot be negative!")
                return
            if user_data['credits'] < bet_amount:
                await update.message.reply_text(f"You need at least {bet_amount} credits to start a game with this bet!")
                return
        except ValueError:
            await update.message.reply_text("Please provide a valid number for the bet amount!")
            return
    
    # Generate random number between 1 and 100
    target = random.randint(1, 100)
    
    # Create game data
    game_data = {
        "user_id": user_id,
        "target": target,
        "bet": bet_amount,
        "multiplier": 1.0,
        "last_move": datetime.utcnow()
    }
    
    # Store game data
    db.hilo_games.insert_one(game_data)
    
    # Create keyboard
    keyboard = [
        [
            InlineKeyboardButton("⬇️ Lower", callback_data=f"hilo_lower_{user_id}"),
            InlineKeyboardButton("⬆️ Higher", callback_data=f"hilo_higher_{user_id}")
        ],
        [InlineKeyboardButton("💰 Cashout", callback_data=f"hilo_cashout_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send game start message
    message = (
        f"🎲 *HiLo Game Started!* 🎲\n\n"
        f"Guess if the next number will be higher or lower than 50.\n"
        f"Current multiplier: 1.0x"
    )
    
    if bet_amount > 0:
        message += f"\n💰 Bet Amount: {bet_amount} credits"
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Handle HiLo choices
async def hilo_click(update: Update, context):
    """Handle HiLo game button clicks."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    action, game_id = query.data.split('_')[1:]
    
    game = db.hilo_games.find_one({"user_id": user_id})
    if not game:
        await query.answer("Game not found!")
        return
    
    # Generate new number
    new_number = random.randint(1, 100)
    old_number = game.get("current_number", 50)
    
    # Update game data
    game["current_number"] = new_number
    game["multiplier"] *= 1.2  # Increase multiplier by 20%
    game["last_move"] = datetime.utcnow()
    db.hilo_games.update_one({"user_id": user_id}, {"$set": game})
    
    # Check if guess was correct
    if (action == "higher" and new_number > old_number) or (action == "lower" and new_number < old_number):
        # Correct guess
        message = (
            f"🎯 *Correct!*\n\n"
            f"Previous number: {old_number}\n"
            f"New number: {new_number}\n"
            f"Current multiplier: {game['multiplier']:.1f}x"
        )
        
        # Create keyboard for next move
        keyboard = [
            [
                InlineKeyboardButton("⬇️ Lower", callback_data=f"hilo_lower_{user_id}"),
                InlineKeyboardButton("⬆️ Higher", callback_data=f"hilo_higher_{user_id}")
            ],
            [InlineKeyboardButton("💰 Cashout", callback_data=f"hilo_cashout_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # Wrong guess - game over
        await hilo_cashout(update, context, game, True)

# Handle Cash Out
async def hilo_cashout(update: Update, context, game=None, lost=False):
    """Handle HiLo game cashout."""
    if not game:
        query = update.callback_query
        user_id = str(update.effective_user.id)
        game = db.hilo_games.find_one({"user_id": user_id})
        
        if not game:
            await query.answer("Game not found!")
            return
    
    user_id = game["user_id"]
    bet_amount = game.get("bet", 0)
    multiplier = game["multiplier"]
    
    # Calculate winnings
    winnings = int(bet_amount * multiplier) if not lost else 0
    
    # Update user credits if it was a betting game
    if bet_amount > 0:
        user_data = game_manager.get_user(user_id)
        if not lost:
            game_manager.update_user(user_id, user_data['credits'] + winnings)
        # Remove game from database
        db.hilo_games.delete_one({"user_id": user_id})
    
    # Build result message
    message = (
        f"🎲 *HiLo Game Over!* 🎲\n\n"
        f"Final multiplier: {multiplier:.1f}x"
    )
    
    if bet_amount > 0:
        if lost:
            message += f"\n❌ You lost {bet_amount} credits!"
        else:
            message += f"\n💰 You won {winnings} credits!"
    
    # Send result message
    if update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")

def get_hilo_handlers():
    """Return all HiLo game handlers."""
    return [
        CommandHandler("hilo", start_hilo),
        CallbackQueryHandler(hilo_click, pattern="^hilo_(lower|higher)_"),
        CallbackQueryHandler(hilo_cashout, pattern="^hilo_cashout_")
    ]
