import logging
import random
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
from pymongo import MongoClient
from collections import Counter

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB connection setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# MongoDB management functions
def get_user_by_id(user_id):
    """
    Fetch user data from the database and ensure default structure.
    """
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        return None

    # Ensure default structure for critical fields
    user_data['bag'] = user_data.get('bag', {"bronze": 0, "silver": 0, "gold": 0})
    
    # Ensure 'cards' is a list
    if not isinstance(user_data.get('cards'), list):
        user_data['cards'] = []

    return user_data


def save_user(user_data):
    """
    Save user data to the database.
    """
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Path to the card directories
NORMAL_CARDS_DIR = "normal_cards"
SPECIAL_CARDS_DIR = "special_cards"

# Coin cost for each pull
NORMAL_PULL_COST = 3  # 3 bronze coins for normal pull
SPECIAL_PULL_COST = 1  # 1 gold coin for special pull

def get_random_card(card_type: str) -> str:
    """
    Get a random card file from the specified card type directory.
    """
    card_dir = NORMAL_CARDS_DIR if card_type == 'normal' else SPECIAL_CARDS_DIR
    card_files = [f for f in os.listdir(card_dir) if f.endswith('.png')]
    return random.choice(card_files) if card_files else None

async def gacha(update: Update, context: CallbackContext) -> None:
    """
    Handle the /gacha command where users can choose to pull a normal or special card.
    """
    user_id = update.effective_user.id
    user_data = get_user_by_id(str(user_id))

    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Create the inline buttons for choosing card types
    keyboard = [
        [InlineKeyboardButton("Normal Pull (3 Bronze Coins)", callback_data="normal")],
        [InlineKeyboardButton("Special Pull (1 Gold Coin)", callback_data="special")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a pull type:", reply_markup=reply_markup)

async def card_pull(update: Update, context: CallbackContext) -> None:
    """
    Handle the callback when a user selects a normal or special pull.
    """
    user_id = update.effective_user.id
    user_data = get_user_by_id(str(user_id))

    if not user_data:
        await update.callback_query.message.reply_text("You need to start the bot first by using /start.")
        await update.callback_query.answer()
        return

    chosen_pull = update.callback_query.data
    coins_key = 'bronze' if chosen_pull == 'normal' else 'gold'
    pull_cost = NORMAL_PULL_COST if chosen_pull == 'normal' else SPECIAL_PULL_COST

    # Check if the user has enough coins
    if user_data['bag'].get(coins_key, 0) < pull_cost:
        await update.callback_query.message.reply_text("Sorry, you don't have enough coins!")
        await update.callback_query.answer()
        return

    # Deduct the cost and get a random card
    user_data['bag'][coins_key] -= pull_cost
    card_file = get_random_card(chosen_pull)

    if card_file:
        card_name = card_file.replace(".png", "").replace("_", " ").title()
        user_data['cards'].append(card_name)
        save_user(user_data)

        card_path = os.path.join(NORMAL_CARDS_DIR if chosen_pull == "normal" else SPECIAL_CARDS_DIR, card_file)
        with open(card_path, 'rb') as card_image:
            await update.callback_query.message.reply_photo(photo=card_image, caption=f"🎉 You pulled a {card_name} card!")
    else:
        await update.callback_query.message.reply_text("Sorry, no cards available.")

    await update.callback_query.answer()
async def my_collection(update: Update, context: CallbackContext) -> None:
    """
    Handle the /mycollection command where users can view their collected cards.
    """
    user_id = update.effective_user.id
    user_data = get_user_by_id(str(user_id))

    if not user_data or not user_data.get('cards', []):
        await update.message.reply_text("You don't have any cards in your collection.")
        return

    # Flatten the card collection for accurate numbering
    card_counts = Counter(user_data['cards'])
    flat_card_list = [card for card, count in card_counts.items() for _ in range(count)]

    # Persist the flat list to MongoDB instead of transient `context.user_data`
    user_data['flat_card_list'] = flat_card_list
    save_user(user_data)

    # Display the collection with accurate numbering
    collection = "\n".join(
        [f"🎴 {i + 1}. *{card}*" for i, card in enumerate(flat_card_list)]
    )
    await update.message.reply_text(f"Your collection:\n\n{collection}", parse_mode="Markdown")


async def view_card(update: Update, context: CallbackContext) -> None:
    try:
        card_number = int(context.args[0]) - 1
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide the number of the card you want to view.")
        return

    user_id = update.effective_user.id
    user_data = get_user_by_id(str(user_id))

    if not user_data or not user_data.get('flat_card_list', []):
        await update.message.reply_text("Your card collection is empty or not loaded.")
        return

    flat_card_list = user_data['flat_card_list']

    if card_number < 0 or card_number >= len(flat_card_list):
        await update.message.reply_text("Invalid card number. Please choose a valid card.")
        return

    card_name = flat_card_list[card_number]
    card_filename = card_name.lower().replace(" ", "_").replace("-", "_") + ".png"

    card_path = os.path.join(NORMAL_CARDS_DIR, card_filename)
    if not os.path.exists(card_path):
        card_path = os.path.join(SPECIAL_CARDS_DIR, card_filename)

    logger.info(f"Looking for card image at: {card_path}")

    try:
        if os.path.exists(card_path):
            with open(card_path, 'rb') as card_image:
                await update.message.reply_photo(photo=card_image, caption=f"🎴 {card_name}")
        else:
            logger.warning(f"Card image not found: {card_filename}")
            await update.message.reply_text(f"Card image for '{card_name}' not found.")
    except Exception as e:
        logger.error(f"Error sending card image: {e}")
        await update.message.reply_text("An error occurred while retrieving the card image.")


