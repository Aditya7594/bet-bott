import os
import random
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient

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
    user_id = update.effective_user.id
    user = game_manager.get_user(user_id)
    credits = user["credits"]

    # Check daily game limit
    if not game_manager.can_play_game(user_id):
        await update.message.reply_text("⏳ You've reached your daily game limit! Come back tomorrow.")
        return

    # Validate bet
    try:
        bet = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("📜 <b>Usage:</b> /hilo <bet amount>", parse_mode="HTML")
        return

    # Bet amount validation
    if bet < game_manager.min_bet or bet > game_manager.max_bet:
        await update.message.reply_text(f"❌ Your bet must be between {game_manager.min_bet} and {game_manager.max_bet} credits!")
        return

    # Check sufficient credits
    if credits < bet:
        await update.message.reply_text("🚫 Not enough credits! Check your balance.")
        return

    # Deduct bet and start game
    game_manager.update_user(user_id, credits - bet)
    player_card = game_manager.start_game(user_id, bet)

    # Create game interface
    buttons = [
        [
            InlineKeyboardButton("⬆️ High", callback_data="hilo_high"), 
            InlineKeyboardButton("⬇️ Low", callback_data="hilo_low")
        ],
        [InlineKeyboardButton("💰 Cash Out", callback_data="hilo_cashout")]
    ]

    card_image_path = resize_card_image(player_card)

    text = (
        f"🎮 <b>HiLo Game</b> 🎮\n\n"
        f"🃏 Your Card: <b>{player_card[1]} of {player_card[0]}</b>\n"
        f"❓ Next Card: <b>Hidden</b>\n\n"
        f"💵 Bet: <b>{bet} credits</b>\n"
        f"🔄 Multiplier: <b>1.0x</b>\n\n"
        f"🤔 <b>Will the next card be higher or lower?</b>"
    )

    with open(card_image_path, "rb") as card_image:
        await update.message.reply_photo(
            photo=card_image, 
            caption=text, 
            reply_markup=InlineKeyboardMarkup(buttons), 
            parse_mode="HTML"
        )

# Handle HiLo choices
async def hilo_click(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in game_manager.games:
        await query.answer("⚠️ No active game found!", show_alert=True)
        return

    choice = query.data.split("_")[-1]
    is_correct, table_card, multiplier = game_manager.process_guess(user_id, choice)

    if is_correct:
        # Successful guess
        buttons = [
            [
                InlineKeyboardButton("⬆️ High", callback_data="hilo_high"), 
                InlineKeyboardButton("⬇️ Low", callback_data="hilo_low")
            ],
            [InlineKeyboardButton("💰 Cash Out", callback_data="hilo_cashout")]
        ]

        text = (
            f"🎮 <b>HiLo Game</b> 🎮\n\n"
            f"✅ <b>Correct!</b>\n"
            f"🃏 Your New Card: <b>{table_card[1]} of {table_card[0]}</b>\n"
            f"❓ Next Card: <b>Hidden</b>\n\n"
            f"🔄 Multiplier: <b>{multiplier:.1f}x</b>\n\n"
            f"🎉 Great guess! Continue or cash out?"
        )

        card_image_path = resize_card_image(table_card)
        with open(card_image_path, "rb") as card_image:
            await query.edit_message_media(
                media=InputMediaPhoto(media=card_image),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await query.edit_message_caption(
                caption=text, 
                parse_mode="HTML", 
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        # Lost the game
        text = (
            f"🎮 <b>HiLo Game</b> 🎮\n\n"
            f"❌ <b>Wrong guess!</b>\n"
            f"🃏 The Table Card was: <b>{table_card[1]} of {table_card[0]}</b>\n\n"
            f"😢 Better luck next time!"
        )

        card_image_path = resize_card_image(table_card)
        with open(card_image_path, "rb") as card_image:
            await query.edit_message_media(
                media=InputMediaPhoto(media=card_image),
                reply_markup=None
            )
            await query.edit_message_caption(
                caption=text, 
                parse_mode="HTML", 
                reply_markup=None
            )

# Handle Cash Out
async def hilo_cashout(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in game_manager.games:
        await query.answer("⚠️ No active game to cash out.", show_alert=True)
        return

    winnings = game_manager.calculate_winnings(user_id)
    user = game_manager.get_user(user_id)

    # Update user credits
    game_manager.update_user(user_id, user['credits'] + winnings)

    text = (
        f"🎮 <b>HiLo Game</b> 🎮\n\n"
        f"💰 <b>Successful Cashout!</b>\n\n"
        f"🏆 Winnings: <b>{winnings} credits</b>\n\n"
        f"🎊 Congratulations and thanks for playing!"
    )
    await query.edit_message_caption(
        caption=text, 
        parse_mode="HTML", 
        reply_markup=None
    )

def get_hilo_handlers():
    """Return all HiLo game handlers."""
    return [
        CommandHandler("hilo", start_hilo),
        CallbackQueryHandler(hilo_click, pattern="hilo_(high|low)"),
        CallbackQueryHandler(hilo_cashout, pattern="hilo_cashout")
    ]
