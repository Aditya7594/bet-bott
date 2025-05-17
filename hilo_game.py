import os
import random
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient
from datetime import datetime

# MongoDB setup
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
        self.max_daily_games = 50
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

# Resize card image function
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
    if update.effective_chat.type != "private":
        await update.message.reply_text("HiLo can only be played in private chat. Please DM the bot to play!")
        return
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
            if bet_amount < game_manager.min_bet:
                await update.message.reply_text(f"Minimum bet amount is {game_manager.min_bet} credits!")
                return
            if bet_amount > game_manager.max_bet:
                await update.message.reply_text(f"Maximum bet amount is {game_manager.max_bet} credits!")
                return
            if user_data['credits'] < bet_amount:
                await update.message.reply_text(f"You need at least {bet_amount} credits to start a game with this bet!")
                return
        except ValueError:
            await update.message.reply_text("Please provide a valid number for the bet amount!")
            return
    
    # Check daily game limit
    if not game_manager.can_play_game(user_id):
        await update.message.reply_text(f"You've reached the daily limit of {game_manager.max_daily_games} games!")
        return
    
    # Start the game
    player_card = game_manager.start_game(user_id, bet_amount)
    
    # Create keyboard
    keyboard = [
        [
            InlineKeyboardButton("⬇️ Lower", callback_data=f"hilo_low_{user_id}"),
            InlineKeyboardButton("⬆️ Higher", callback_data=f"hilo_high_{user_id}")
        ],
        [InlineKeyboardButton("💰 Cashout", callback_data=f"hilo_cashout_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send game start message with card image
    try:
        card_path = resize_card_image(player_card)
        with open(card_path, 'rb') as card_file:
            await update.message.reply_photo(
                photo=card_file,
                caption=(
                    f"🎴 *HiLo Game Started!* 🎴\n\n"
                    f"Your card: {player_card[1]} of {player_card[0]}\n"
                    f"Current multiplier: {game_manager.base_multiplier}x"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(
            f"🎴 *HiLo Game Started!* 🎴\n\n"
            f"Your card: {player_card[1]} of {player_card[0]}\n"
            f"Current multiplier: {game_manager.base_multiplier}x",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

# Handle HiLo choices
async def hilo_click(update: Update, context):
    """Handle HiLo game button clicks."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    action, game_id = query.data.split('_')[1:]
    
    # Process the guess
    is_correct, table_card, multiplier = game_manager.process_guess(user_id, action)
    
    if is_correct is None:
        await query.answer("Game not found!")
        return
    
    # Create keyboard for next move
    keyboard = [
        [
            InlineKeyboardButton("⬇️ Lower", callback_data=f"hilo_low_{user_id}"),
            InlineKeyboardButton("⬆️ Higher", callback_data=f"hilo_high_{user_id}")
        ],
        [InlineKeyboardButton("💰 Cashout", callback_data=f"hilo_cashout_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_correct:
        # Correct guess - show new card and continue
        try:
            card_path = resize_card_image(table_card)
            with open(card_path, 'rb') as card_file:
                await query.message.edit_media(
                    media=InputMediaPhoto(
                        media=card_file,
                        caption=(
                            f"🎴 *Correct!* 🎴\n\n"
                            f"Your card: {table_card[1]} of {table_card[0]}\n"
                            f"Current multiplier: {multiplier}x"
                        ),
                        parse_mode="Markdown"
                    ),
                    reply_markup=reply_markup
                )
        except Exception as e:
            await query.message.edit_text(
                f"🎴 *Correct!* 🎴\n\n"
                f"Your card: {table_card[1]} of {table_card[0]}\n"
                f"Current multiplier: {multiplier}x",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    else:
        # Wrong guess - game over
        await hilo_cashout(update, context, True)

# Handle Cash Out
async def hilo_cashout(update: Update, context, lost=False):
    """Handle HiLo game cashout."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    
    # Calculate winnings
    winnings = game_manager.calculate_winnings(user_id)
    
    # Update user credits if it was a betting game
    if winnings > 0:
        user_data = game_manager.get_user(user_id)
        if not lost:
            game_manager.update_user(user_id, user_data['credits'] + winnings)
    
    # Build result message
    message = (
        f"🎴 *HiLo Game Over!* 🎴\n\n"
        f"Final multiplier: {game_manager.games.get(user_id, {}).get('multiplier', 1.0):.1f}x"
    )
    
    if winnings > 0:
        if lost:
            message += f"\n❌ You lost {game_manager.games.get(user_id, {}).get('bet', 0)} credits!"
        else:
            message += f"\n💰 You won {winnings} credits!"
    
    await query.edit_message_text(message, parse_mode="Markdown")

def get_hilo_handlers():
    """Return all HiLo game handlers."""
    return [
        CommandHandler("hilo", start_hilo),
        CallbackQueryHandler(hilo_click, pattern="^hilo_(low|high)_"),
        CallbackQueryHandler(hilo_cashout, pattern="^hilo_cashout_")
    ]