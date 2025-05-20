from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
import os
from PIL import Image
import math
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
import random

# Connect to MongoDB
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
user_collection = db['users']
shop_collection = db['shop']

# Bot settings
BOT_OWNER_ID = "5667016949"  # Replace with your Telegram ID
BASE_PRICE = 1000000  # 1 million credits
SUNDAY_DISCOUNT = 0.5  # 50% off on Sundays
COMPENSATION_CARDS = 2  # Number of cards to give as compensation


def get_next_reset_time():
    """Get the next reset time in IST"""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # If it's past midnight, next reset is tomorrow at midnight
    if now.hour >= 0:
        next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    return next_reset

def format_time_remaining():
    """Format the remaining time until next reset"""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    next_reset = get_next_reset_time()
    
    time_diff = next_reset - now
    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)
    
    return f"{hours} hours and {minutes} minutes"

def reset_shop_data():
    """Reset all shop data to ensure fresh start"""
    shop_collection.delete_many({})
    print("Shop data has been reset")

def get_current_price():
    """Get current price based on day of week"""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    # Check if it's Sunday
    if current_time.weekday() == 6:  # 6 is Sunday
        return int(BASE_PRICE * SUNDAY_DISCOUNT)
    return BASE_PRICE

def get_user_shop(user_id: str):
    """Get personalized shop for a specific user"""
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist).date()
    
    # Check if user has a shop for today
    shop_data = shop_collection.find_one({
        "date": str(today),
        "user_id": user_id
    })
    
    if not shop_data:
        # Get all available shop images
        shop_images = [f for f in os.listdir('shop') if f.endswith('.jpg')]
        
        # Randomly select 4 cards for this user
        selected_images = random.sample(shop_images, min(4, len(shop_images)))
        
        # Create daily cards for this user
        daily_cards = {}
        for img in selected_images:
            card_id = img.replace('.jpg', '')
            daily_cards[card_id] = {
                'name': card_id,  # Use the actual image name without .jpg
                'image': f'shop/{img}',
                'price': get_current_price(),
                'stats': CARD_STATS.get(card_id, {"batting": 75, "bowling": 75, "fielding": 75})
            }
        
        # Update shop collection with user-specific data
        shop_collection.update_one(
            {
                "date": str(today),
                "user_id": user_id
            },
            {"$set": {"cards": daily_cards}},
            upsert=True
        )
        return daily_cards
    
    return shop_data.get('cards', {})

async def reset_collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resetcollection command to reset user's collection and give compensation cards"""
    user_id = str(update.effective_user.id)
    
    # Check if user is the bot owner
    if user_id != BOT_OWNER_ID:
        await update.message.reply_text("❌ This command can only be used by the bot owner.")
        return
    
    # Check if target user is specified
    if not context.args:
        await update.message.reply_text("Please specify a user ID: /resetcollection <user_id>")
        return
    
    target_user_id = context.args[0]
    user_data = user_collection.find_one({"user_id": target_user_id})
    
    if not user_data:
        await update.message.reply_text("❌ User not found in database.")
        return
    
    # Get all available shop images
    shop_images = [f for f in os.listdir('shop') if f.endswith('.jpg')]
    
    # Randomly select compensation cards
    selected_images = random.sample(shop_images, min(COMPENSATION_CARDS, len(shop_images)))
    
    # Create new cards for compensation
    new_cards = []
    for img in selected_images:
        card_id = img.replace('.jpg', '')
        new_cards.append({
            "id": card_id,
            "name": card_id,
            "image": f'shop/{img}'
        })
    
    # Update user's collection with new cards
    user_collection.update_one(
        {"user_id": target_user_id},
        {"$set": {"cards": new_cards}}
    )
    
    # Format message showing new cards
    message = f"🔄 Collection reset for user {target_user_id}!\n\n"
    message += "🎁 They received these new cards as compensation:\n"
    for card in new_cards:
        message += f"• {card['name']}\n"
    
    await update.message.reply_text(message)

async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /shop command to display daily available cards"""
    user_id = str(update.effective_user.id)
    user_data = user_collection.find_one({"user_id": user_id})
    
    if not user_data:
        await update.message.reply_text("Please use /start first to initialize your account.")
        return
    
    credits = user_data.get('credits', 0)
    daily_cards = get_user_shop(user_id)  # Get personalized shop
    
    # Check if it's Sunday
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    is_sunday = current_time.weekday() == 6
    
    # Create inline keyboard with buy buttons
    keyboard = []
    for card_id, card_data in daily_cards.items():
        button = InlineKeyboardButton(
            f"Buy {card_data['name']} - {card_data['price']:,} credits",
            callback_data=f"buy_{card_id}"
        )
        keyboard.append([button])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Format shop message with reset timer
    shop_text = f"🎮 Your Personal Card Shop 🎮\n"
    shop_text += f"⏰ Shop resets in: {format_time_remaining()}\n"
    shop_text += f"💰 Your Credits: {credits:,}\n\n"
    
    if is_sunday:
        shop_text += "🎉 *SUNDAY SPECIAL! 50% OFF ALL CARDS!* 🎉\n\n"
    
    shop_text += "Today's Available Cards:\n" + "\n".join([
        f"• {card['name']} - {card['price']:,} credits" 
        for card in daily_cards.values()
    ])
    
    await update.message.reply_text(
        shop_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle buy button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    card_id = query.data.split('_')[1]
    
    # Get user's personal shop
    daily_cards = get_user_shop(user_id)
    if card_id not in daily_cards:
        await query.edit_message_text("❌ This card is no longer available in your shop.")
        return
    
    card_data = daily_cards[card_id]
    
    # Get user data
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await query.edit_message_text("Please use /start first to initialize your account.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < card_data['price']:
        await query.edit_message_text(
            f"❌ Not enough credits! You need {card_data['price']:,} credits to buy {card_data['name']}."
        )
        return
    
    # Process purchase
    try:
        # Update user's credits
        user_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"credits": -card_data['price']}}
        )
        
        # Add card to user's collection
        user_collection.update_one(
            {"user_id": user_id},
            {"$push": {"cards": {
                "id": card_id,
                "name": card_data['name'],
                "image": card_data['image'],
                "stats": card_data['stats']
            }}}
        )
        
        await query.edit_message_text(
            f"✅ Successfully purchased {card_data['name']} for {card_data['price']:,} credits!"
        )
    except Exception as e:
        await query.edit_message_text("❌ An error occurred while processing your purchase.")

async def mycollection_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mycollection command to show user's cards"""
    user_id = str(update.effective_user.id)
    user_data = user_collection.find_one({"user_id": user_id})
    
    if not user_data:
        await update.message.reply_text("Please use /start first to initialize your account.")
        return
    
    cards = user_data.get('cards', [])
    if not cards:
        await update.message.reply_text("Your collection is empty. Visit the shop to buy some cards!")
        return
    
    # Format collection message
    collection_text = "🎴 Your Collection:\n\n"
    for card in cards:
        collection_text += f"• {card['name']}\n"
    
    await update.message.reply_text(collection_text)

async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /view command to show a specific player card"""
    if not context.args:
        await update.message.reply_text("Please specify a player name: /view <player_name>")
        return
    
    user_id = str(update.effective_user.id)
    player_name = ' '.join(context.args)
    
    # Get user's collection
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("Please use /start first to initialize your account.")
        return
    
    cards = user_data.get('cards', [])
    card = next((c for c in cards if c['name'].lower() == player_name.lower()), None)
    
    if not card:
        await update.message.reply_text(f"Card '{player_name}' not found in your collection.")
        return
    
    # Create inline keyboard with "Set as Main" button
    keyboard = [[InlineKeyboardButton("Set as Main", callback_data=f"setmain_{card['id']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send card image
    with open(card['image'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption=f"🎴 Card Details:\nName: {card['name']}",
            reply_markup=reply_markup
        )

async def setmain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setmain button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    card_id = query.data.split('_')[1]
    
    # Get user's collection
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await query.edit_message_text("Please use /start first to initialize your account.")
        return
    
    cards = user_data.get('cards', [])
    card = next((c for c in cards if c['id'] == card_id), None)
    
    if not card:
        await query.edit_message_text("❌ Card not found in your collection.")
        return
    
    # Update user's main card
    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"main_card": card}}
    )
    
    await query.edit_message_text(f"✅ {card['name']} set as your main card!")

async def manage_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /managecards command for bot owner"""
    user_id = str(update.effective_user.id)
    
    # Check if user is the bot owner
    if user_id != BOT_OWNER_ID:
        await update.message.reply_text("❌ This command can only be used by the bot owner.")
        return
    
    # Check if command is a reply
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please reply to a user's message with:\n"
            "/managecards add <card_name>\n"
            "or\n"
            "/managecards remove <card_name>"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/managecards add <card_name>\n"
            "/managecards remove <card_name>"
        )
        return
    
    action = context.args[0].lower()
    if action not in ['add', 'remove']:
        await update.message.reply_text("Invalid action! Use 'add' or 'remove'.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Please provide a card name.")
        return
    
    target_user_id = str(update.message.reply_to_message.from_user.id)
    card_name = ' '.join(context.args[1:])
    
    # Check if user exists
    user_data = user_collection.find_one({"user_id": target_user_id})
    if not user_data:
        await update.message.reply_text("❌ User not found in database.")
        return
    
    # Check if card image exists
    card_image = f"shop/{card_name}.jpg"
    if not os.path.exists(card_image):
        await update.message.reply_text(f"❌ Card image not found: {card_image}")
        return
    
    if action == 'add':
        # Add card to user's collection
        card_data = {
            "id": card_name,
            "name": card_name,
            "image": card_image,
            "stats": CARD_STATS.get(card_name, {"batting": 75, "bowling": 75, "fielding": 75})
        }
        
        # Check if card already exists
        if any(c['id'] == card_name for c in user_data.get('cards', [])):
            await update.message.reply_text(f"❌ User already has this card.")
            return
        
        user_collection.update_one(
            {"user_id": target_user_id},
            {"$push": {"cards": card_data}}
        )
        await update.message.reply_text(f"✅ Added {card_name} to {update.message.reply_to_message.from_user.first_name}'s collection.")
        
    else:  # remove
        # Remove card from user's collection
        result = user_collection.update_one(
            {"user_id": target_user_id},
            {"$pull": {"cards": {"id": card_name}}}
        )
        
        if result.modified_count > 0:
            # If removed card was main card, clear main card
            if user_data.get('main_card', {}).get('id') == card_name:
                user_collection.update_one(
                    {"user_id": target_user_id},
                    {"$unset": {"main_card": ""}}
                )
            await update.message.reply_text(f"✅ Removed {card_name} from {update.message.reply_to_message.from_user.first_name}'s collection.")
        else:
            await update.message.reply_text(f"❌ Card not found in user's collection.")

def get_shop_handlers():
    return [
        CommandHandler("shop", shop_command),
        CommandHandler("mycollection", mycollection_command),
        CommandHandler("view", view_command),
        CommandHandler("managecards", manage_cards),
        CommandHandler("resetcollection", reset_collection_command),
        CallbackQueryHandler(buy_callback, pattern="^buy_"),
        CallbackQueryHandler(setmain_callback, pattern="^setmain_"),
    ] 