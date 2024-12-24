import os
import random
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Card deck setup
CARD_VALUES = {'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13}
SUITS = ['diamonds', 'hearts', 'clubs', 'spades']
DECK = [(suit, value) for suit in SUITS for value in CARD_VALUES.keys()]

# Game state tracking
games = {}
daily_limits = {}

# MongoDB helper functions
def get_user(user_id):
    user = users_collection.find_one({"user_id": str(user_id)})
    if not user:
        user = {"user_id": str(user_id), "credits": 1000}  # Default starting credits
        users_collection.insert_one(user)
    return user

def update_user(user_id, credits):
    users_collection.update_one({"user_id": str(user_id)}, {"$set": {"credits": credits}}, upsert=True)

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

# Start HiLo game
# Start HiLo game
async def start_hilo(update: Update, context):
    user_id = update.effective_user.id
    user = get_user(user_id)
    credits = user["credits"]

    if user_id not in daily_limits:
        daily_limits[user_id] = 0

    if daily_limits[user_id] >= 5:
        await update.message.reply_text("⏳ You've reached your daily limit of games! Come back tomorrow for more fun!")
        return

    try:
        bet = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("📜 <b>Usage:</b> /hilo <bet amount>\n\n💡 Place your bets between 100 and 10,000 credits to begin the game!", parse_mode="HTML")
        return

    if bet < 100 or bet > 10000:
        await update.message.reply_text("❌ Your bet must be between 100 and 10,000 credits! Try again.")
        return

    if credits < bet:
        await update.message.reply_text("🚫 You don't have enough credits to place this bet! Check your balance and try again.")
        return

    update_user(user_id, credits - bet)

    player_card = random.choice(DECK)

    games[user_id] = {
        "bet": bet,
        "player_card": player_card,
        "multiplier": 1.0,
    }

    buttons = [
        [InlineKeyboardButton("⬆️ High", callback_data="hilo_high"), InlineKeyboardButton("⬇️ Low", callback_data="hilo_low")],
        [InlineKeyboardButton("💰 Cash Out", callback_data="hilo_cashout")],
    ]

    card_image_path = resize_card_image(player_card)

    text = (
        f"🎮 <b>HiLo Game</b> 🎮\n\n"
        f"🃏 Your Card: <b>{player_card[1]} of {player_card[0]}</b>\n"
        f"❓ Table Card: <b>Hidden</b>\n\n"
        f"💵 Bet: <b>{bet} credits</b>\n"
        f"🔄 Multiplier: <b>1.0x</b>\n\n"
        f"🤔 <b>Will the next card be higher or lower?</b>\n"
    )

    with open(card_image_path, "rb") as card_image:
        await update.message.reply_photo(photo=card_image, caption=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

# Handle HiLo choices
async def hilo_click(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in games:
        await query.answer("⚠️ No active game found! Start a new game with /hilo <bet amount>.", show_alert=True)
        return

    game = games[user_id]
    player_card = game["player_card"]
    table_card = random.choice(DECK)
    bet = game["bet"]

    player_value = CARD_VALUES[player_card[1]]
    table_value = CARD_VALUES[table_card[1]]
    choice = query.data.split("_")[-1]

    if (choice == "high" and table_value > player_value) or (choice == "low" and table_value < player_value):
        game["player_card"] = table_card
        game["multiplier"] += 0.4

        buttons = [
            [InlineKeyboardButton("⬆️ High", callback_data="hilo_high"), InlineKeyboardButton("⬇️ Low", callback_data="hilo_low")],
            [InlineKeyboardButton("💰 Cash Out", callback_data="hilo_cashout")],
        ]

        text = (
            f"🎮 <b>HiLo Game</b> 🎮\n\n"
            f"✅ <b>Correct!</b>\n"
            f"🃏 Your New Card: <b>{table_card[1]} of {table_card[0]}</b>\n"
            f"❓ Table Card: <b>Hidden</b>\n\n"
            f"💵 Bet: <b>{bet} credits</b>\n"
            f"🔄 Multiplier: <b>{round(game['multiplier'], 2)}x</b>\n\n"
            f"🎉 Great guess! Will the next card be higher or lower?\n"
        )

        card_image_path = resize_card_image(table_card)
        with open(card_image_path, "rb") as card_image:
            await query.edit_message_media(
                media=InputMediaPhoto(media=card_image),
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        del games[user_id]
        daily_limits[user_id] += 1

        text = (
            f"🎮 <b>HiLo Game</b> 🎮\n\n"
            f"❌ <b>Wrong guess!</b>\n"
            f"🃏 The Table Card was: <b>{table_card[1]} of {table_card[0]}</b>\n\n"
            f"💵 Bet: <b>{bet} credits</b>\n\n"
            f"😢 Better luck next time!"
        )
        buttons = []  # Remove buttons after losing
        card_image_path = resize_card_image(table_card)
        with open(card_image_path, "rb") as card_image:
            await query.edit_message_media(
                media=InputMediaPhoto(media=card_image),
                reply_markup=None,
            )
            await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=None)

# Handle Cash Out
async def hilo_cashout(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in games:
        await query.answer("⚠️ No active game found to cash out.", show_alert=True)
        return

    game = games.pop(user_id)
    winnings = round(game["bet"] * game["multiplier"])
    user = get_user(user_id)

    update_user(user_id, user["credits"] + winnings)
    daily_limits[user_id] += 1

    text = (
        f"🎮 <b>HiLo Game</b> 🎮\n\n"
        f"💰 <b>You cashed out successfully!</b>\n\n"
        f"🏆 Winnings: <b>{winnings} credits</b>\n\n"
        f"🎊 Congratulations and thanks for playing! See you again soon!"
    )
    await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=None)
