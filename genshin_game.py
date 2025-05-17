from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext,CommandHandler,CallbackQueryHandler
import random
from pymongo import MongoClient
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple
from telegram.ext import JobQueue
import os

OWNER_ID = 5667016949
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
user_collection = db["users"]
genshin_collection = db["genshin_users"]
group_settings = db["group_settings"]  # New collection for group settings

CHARACTERS = {
    # 5-star characters
    "Albedo": 5, "Alhaitham": 5, "Aloy": 5, "Ayaka": 5, "Ayato": 5, "Baizhu": 5, "Cyno": 5, 
    "Dehya": 5, "Diluc": 5, "Eula": 5, "Ganyu": 5, "Hu Tao": 5, "Itto": 5, "Jean": 5, 
    "Kazuha": 5, "Keqing": 5, "Klee": 5, "Kokomi": 5, "Lyney": 5, "Mona": 5, "Nahida": 5, 
    "Nilou": 5, "Qiqi": 5, "Raiden": 5, "Shenhe": 5, "Tighnari": 5, "Venti": 5, "Wanderer": 5, 
    "Xiao": 5, "Yae Miko": 5, "Yelan": 5, "Yoimiya": 5, "Zhongli": 5,
    # 4-star characters
    "Amber": 4, "Barbara": 4, "Beidou": 4, "Bennett": 4, "Candace": 4, "Chongyun": 4, 
    "Collei": 4, "Diona": 4, "Dori": 4, "Fischl": 4, "Gorou": 4, "Heizou": 4, "Kaeya": 4, 
    "Kuki Shinobu": 4, "Layla": 4, "Lisa": 4, "Ningguang": 4, "Noelle": 4, "Razor": 4, 
    "Rosaria": 4, "Sara": 4, "Sayu": 4, "Sucrose": 4, "Thoma": 4, "Xiangling": 4, 
    "Xingqiu": 4, "Xinyan": 4, "Yanfei": 4, "Yaoyao": 4, "Yun Jin": 4
}
# Comprehensive list of weapons with their star ratings
WEAPONS = {
    # 5-star weapons
    "Aquila Favonia": 5, "Amos' Bow": 5, "Aqua Simulacra": 5, "Calamity Queller": 5, "Crimson Moon's Semblance": 5,
    "Elegy for the End": 5, "Engulfing Lightning": 5, "Everlasting Moonglow": 5, "Freedom-Sword": 5,
    "Haran Geppaku Futsu": 5, "Hunter's Path": 5, "Jadefall's Splendor": 5, "Kagura's Verity": 5,
    "Key of Khaj-Nisut": 5, "Light of Foliar Incision": 5, "Lost Prayer to the Sacred Winds": 5,
    "Lumidouce Elegy": 5, "Memory of Dust": 5, "Mistsplitter Reforged": 5, "Polar Star": 5,
    "Primordial Jade Cutter": 5, "Primordial Jade Winged-Spear": 5, "Redhorn Stonethresher": 5,
    "Song of Broken Pines": 5, "Staff of Homa": 5, "Staff of the Scarlet Sands": 5, "Summit Shaper": 5,
    "The First Great Magic": 5, "The Unforged": 5, "Thundering Pulse": 5, "Tome of the Eternal Flow": 5,
    "Tulaytullah's Remembrance": 5, "Uraku Misugiri": 5, "Verdict": 5, "Vortex Vanquisher": 5, "Wolf's Gravestone": 5,
    # 4-star weapons
    "Akuoumaru": 4, "Alley Hunter": 4, "Amenoma Kageuchi": 4, "Ballad of the Boundless Blue": 4,
    "Ballad of the Fjords": 4, "Blackcliff Agate": 4, "Blackcliff Longsword": 4, "Blackcliff Pole": 4,
    "Blackcliff Slasher": 4, "Blackcliff Warbow": 4, "Cloudforged": 4, "Cinnabar Spindle": 4,
    "Compound Bow": 4, "Crescent Pike": 4, "Deathmatch": 4, "Dodoco Tales": 4, "Dragon's Bane": 4,
    "Dragonspine Spear": 4, "End of the Line": 4, "Eye of Perception": 4, "Fading Twilight": 4,
    "Favonius Codex": 4, "Favonius Greatsword": 4, "Favonius Lance": 4, "Favonius Sword": 4,
    "Favonius Warbow": 4, "Festering Desire": 4, "Finale of the Deep": 4, "Fleuve Cendre Ferryman": 4,
    "Flowing Purity": 4, "Forest Regalia": 4, "Frostbearer": 4, "Fruit of Fulfillment": 4, "Hakushin Ring": 4,
    "Hamayumi": 4, "Iron Sting": 4, "Kagotsurube Isshin": 4, "Kitain Cross Spear": 4, "Lion's Roar": 4,
    "Lithic Blade": 4, "Lithic Spear": 4, "Luxurious Sea-Lord": 4, "Mailed Flower": 4, "Makhaira Aquamarine": 4,
    "Mappa Mare": 4, "Missive Windspear": 4, "Mitternachts Waltz": 4, "Moonpiercer": 4, "Mouun's Moon": 4,
    "Oathsworn Eye": 4, "Portable Power Saw": 4, "Predator": 4, "Prospector's Drill": 4, "Prototype Amber": 4,
    "Prototype Archaic": 4, "Prototype Crescent": 4, "Prototype Rancour": 4, "Prototype Starglitter": 4,
    "Rainslasher": 4, "Range Gauge": 4, "Rightful Reward": 4, "Royal Bow": 4, "Royal Greatsword": 4,
    "Royal Grimoire": 4, "Royal Longsword": 4, "Royal Spear": 4, "Rust": 4, "Sacrificial Bow": 4,
    "Sacrificial Fragments": 4, "Sacrificial Greatsword": 4, "Sacrificial Jade": 4, "Sacrificial Sword": 4,
    "Sapwood Blade": 4, "Scion of the Blazing Sun": 4, "Serpent Spine": 4, "Snow-Tombed Starsilver": 4,
    "Solar Pearl": 4, "Song of Stillness": 4, "Sword of Descension": 4, "Sword of Narzissenkreuz": 4,
    "Talking Stick": 4, "The Alley Flash": 4, "The Bell": 4, "The Black Sword": 4, "The Catch": 4,
    "The Dockhand's Assistant": 4, "The Flute": 4, "The Stringless": 4, "The Viridescent Hunt": 4,
    "The Widsith": 4, "Tidal Shadow": 4, "Toukabou Shigure": 4, "Ultimate Overlord's Mega Magic Sword": 4,
    "Wandering Evenstar": 4, "Wavebreaker's Fin": 4, "Whiteblind": 4, "Windblume Ode": 4, "Wine and Song": 4,
    "Wolf-Fang": 4, "Xiphos' Moonlight": 4,
    # 3-star weapons
    "Black Tassel": 3, "Bloodtainted Greatsword": 3, "Cool Steel": 3, "Dark Iron Sword": 3,
    "Debate Club": 3, "Emerald Orb": 3, "Ferrous Shadow": 3, "Fillet Blade": 3, "Halberd": 3,
    "Harbinger of Dawn": 3, "Magic Guide": 3, "Messenger": 3, "Otherworldly Story": 3,
    "Raven Bow": 3, "Recurve Bow": 3, "Sharpshooter's Oath": 3, "Skyrider Greatsword": 3,
    "Skyrider Sword": 3, "Slingshot": 3, "Thrilling Tales of Dragon Slayers": 3, "Traveler's Handy Sword": 3,
    "Twin Nephrite": 3, "White Iron Greatsword": 3, "White Tassel": 3
}

ARTIFACTS_FOLDER = "artifacts"
ARTIFACTS = {os.path.splitext(file)[0].replace("_", " "): os.path.join(ARTIFACTS_FOLDER, file) for file in os.listdir(ARTIFACTS_FOLDER) if file.endswith(".png")}

message_counts = {}
last_artifact_time = {}

def get_genshin_user_by_id(user_id):
    return genshin_collection.find_one({"user_id": user_id})
def save_genshin_user(user_data):
    genshin_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)
# Function to get user data from the general users collection
def get_user_by_id(user_id):
    return user_collection.find_one({"user_id": user_id})
# Function to save user data to the general users collection
def save_user(user_data):
    user_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    first_name = user.first_name  # Fetch user's first name for genshin_users collection

    # Save in general users collection
    existing_user = get_user_by_id(user_id)
    if existing_user is None:
        new_user = {
            "user_id": user_id,
            "join_date": datetime.now().strftime('%m/%d/%y'),
            "credits": 5000,  # Assuming credits should be used here
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "primos": 0,
            "bag": {}
        }
        save_user(new_user)
        logger.info(f"User {user_id} started the bot.")
        await update.message.reply_text(
            "Welcome! You've received 5000 credits to start betting. Use /profile to check your details."
        )
    else:
        logger.info(f"User {user_id} already exists.")
        await update.message.reply_text(
            "You have already started the bot. Use /profile to view your details."
        )

    # Save in genshin_users collection
    existing_genshin_user = get_genshin_user_by_id(user_id)
    if existing_genshin_user is None:
        now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # Convert to IST
        today_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
        if now < today_5am:  # Adjust to the previous day's 5:00 AM if before reset
            today_5am -= timedelta(days=1)

        new_genshin_user = {
            "user_id": user_id,
            "first_name": first_name,
            "primos": 16000,  # Initial primogems
            "bag": {"artifacts": {}},
            "daily_earned": 0,        # New field to track daily earned primogems
            "last_reset": today_5am,  # New field to track the last reset time
        }
        save_genshin_user(new_genshin_user)
        logger.info(f"Genshin user {user_id} initialized.")


async def reward_primos(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    user_data = get_genshin_user_by_id(user_id) or {
        "user_id": user_id,
        "primos": 0,
        "bag": {}
    }
    
    user_data["primos"] += 5
    save_genshin_user(user_data)
    
def get_group_settings(chat_id: int) -> dict:
    """Get group settings, or create default if not exists."""
    settings = group_settings.find_one({"chat_id": chat_id})
    if not settings:
        settings = {
            "_id": chat_id,
            "chat_id": chat_id,
            "artifact_threshold": 50,  # Default threshold
            "artifact_enabled": True,   # Default enabled
            "last_artifact_time": None
        }
        group_settings.insert_one(settings)
    return settings

def update_group_settings(chat_id: int, settings: dict):
    """Update group settings."""
    group_settings.update_one(
        {"chat_id": chat_id},
        {"$set": settings},
        upsert=True
    )

async def handle_genshin_group_message(update: Update, context: CallbackContext):
    """Handle messages in groups for primogem rewards."""
    user = update.effective_user
    user_id = str(user.id)
    chat_id = str(update.effective_chat.id)
    
    # Determine message type using message attributes
    message_type = "text"
    if update.message.sticker:
        message_type = "sticker"
    elif update.message.photo:
        message_type = "photo"
    elif update.message.video:
        message_type = "video"
    elif update.message.document:
        message_type = "document"
    elif update.message.audio:
        message_type = "audio"
    elif update.message.voice:
        message_type = "voice"
    elif update.message.animation:
        message_type = "animation"

    logger.info(f"Processing message - User: {user_id}, Chat: {chat_id}, Type: {message_type}")

    if update.effective_chat.type not in ["group", "supergroup"]:
        logger.info(f"Skipping message - Not a group chat. Chat type: {update.effective_chat.type}")
        return

    # Handle artifact system first
    if chat_id not in message_counts:
        message_counts[chat_id] = 0
    message_counts[chat_id] += 1
    threshold = 100  # Default threshold
    now = datetime.now(timezone.utc)
    if chat_id in last_artifact_time:
        time_since_last = (now - last_artifact_time[chat_id]).total_seconds()
        if time_since_last < 300:  # 5 minutes in seconds
            logger.info(f"Not enough time since last artifact in chat {chat_id}")
            # Do not return here, continue to primogem logic
    if message_counts[chat_id] >= threshold:
        message_counts[chat_id] = 0
        logger.info(f"Threshold reached for chat {chat_id}, sending artifact reward")
        await send_artifact_reward(chat_id, context)

    # Primogem reward logic (always run for every message)
    user_data = get_genshin_user_by_id(user_id)
    now = datetime.now(timezone.utc)
    if not user_data:
        logger.info(f"Creating new user data for user {user_id}")
        user_data = {
            "user_id": user_id,
            "primos": 0,
            "bag": {},
            "message_primo": {
                "count": 0,
                "earned": 0,
                "last_reset": now
            }
        }
        save_genshin_user(user_data)
        return
    if "message_primo" not in user_data:
        logger.info(f"Initializing message_primo for user {user_id}")
        user_data["message_primo"] = {
            "count": 0,
            "earned": 0,
            "last_reset": now
        }
    elif user_data["message_primo"].get("last_reset") is None:
        logger.info(f"Setting last_reset for user {user_id}")
        user_data["message_primo"]["last_reset"] = now
    last_reset = user_data["message_primo"]["last_reset"]
    if isinstance(last_reset, datetime) and last_reset.tzinfo is None:
        logger.info(f"Converting last_reset to timezone-aware for user {user_id}")
        last_reset = last_reset.replace(tzinfo=timezone.utc)
        user_data["message_primo"]["last_reset"] = last_reset
    time_diff = (now - last_reset).total_seconds()
    logger.info(f"Time since last reset for user {user_id}: {time_diff} seconds")
    if time_diff > 3600:
        logger.info(f"Resetting message count for user {user_id}")
        user_data["message_primo"]["count"] = 0
        user_data["message_primo"]["earned"] = 0
        user_data["message_primo"]["last_reset"] = now
    current_earned = user_data["message_primo"]["earned"]
    logger.info(f"Current earned primos for user {user_id}: {current_earned}")
    if current_earned < 100:
        user_data["message_primo"]["count"] += 1
        user_data["message_primo"]["earned"] += 5
        user_data["primos"] = user_data.get("primos", 0) + 5
        logger.info(f"Awarded 5 primos to user {user_id}. New total: {user_data['primos']}")
    else:
        logger.info(f"User {user_id} has reached hourly limit of 100 primos")
    save_genshin_user(user_data)
    logger.info(f"Saved updated user data for user {user_id}")

async def set_threshold(update: Update, context: CallbackContext) -> None:
    """Set the artifact drop threshold for a group."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❗ This command can only be used in groups.")
        return

    # Check if user is admin
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    
    if chat_member.status not in ["creator", "administrator"]:
        await update.message.reply_text("❗ Only administrators can use this command.")
        return

    try:
        threshold = int(context.args[0])
        if not 10 <= threshold <= 100:
            raise ValueError("Threshold out of range")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setthreshold <number>")
        return

    # Update group settings
    settings = get_group_settings(chat_id)
    settings["artifact_threshold"] = threshold
    update_group_settings(chat_id, settings)

    await update.message.reply_text(f"✅ Artifact threshold set to {threshold} messages.")

async def toggle_artifacts(update: Update, context: CallbackContext) -> None:
    """Toggle the artifact system on or off for a group."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❗ This command can only be used in groups.")
        return

    # Check if user is admin
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    
    if chat_member.status not in ['creator', 'administrator']:
        await update.message.reply_text("❗ Only administrators can use this command.")
        return

    # Toggle artifact system
    settings = get_group_settings(chat_id)
    current_state = settings.get("artifact_enabled", True)
    settings["artifact_enabled"] = not current_state
    update_group_settings(chat_id, settings)

    status = "enabled" if settings["artifact_enabled"] else "disabled"
    await update.message.reply_text(f"✅ Artifact system has been {status}.")

async def artifact_settings(update: Update, context: CallbackContext) -> None:
    """Display the current artifact system settings for a group."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❗ This command can only be used in groups.")
        return

    # Get group settings
    chat_id = update.effective_chat.id
    settings = get_group_settings(chat_id)

    # Create settings message
    message = (
        "🎮 *Artifact System Settings*\n\n"
        f"Status: {'✅ Enabled' if settings.get('artifact_enabled', True) else '❌ Disabled'}\n"
        f"Message Threshold: {settings.get('artifact_threshold', 50)} messages\n"
        f"Messages until next artifact: {settings.get('artifact_threshold', 50) - message_counts.get(chat_id, 0)}\n\n"
        "*Admin Commands:*\n"
        "/setthreshold <number> - Set message threshold\n"
        "/toggleartifacts - Enable/disable artifacts"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def send_artifact_reward(chat_id: str, context: CallbackContext):
    """Send artifact reward to the group."""
    try:
        # Get random artifact
        artifact = random.choice(list(ARTIFACTS.keys()))
        artifact_image = ARTIFACTS[artifact]
        
        # Create artifact message
        message = (
            f"🎉 <b>Artifact Found!</b>\n\n"
            f"<b>{artifact}</b>\n\n"
            f"Click the button below to claim it!"
        )
        
        # Send message with claim button
        keyboard = [[InlineKeyboardButton("Claim", callback_data=f"claim_artifact_{artifact}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=open(artifact_image, "rb"),
            caption=message,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
        # Update last artifact time
        last_artifact_time[chat_id] = datetime.now(timezone.utc)
        
    except Exception as e:
        logger.error(f"Error sending artifact reward: {e}")

async def handle_artifact_button(update: Update, context: CallbackContext) -> None:
    """Handle the action when a user clicks the 'Get' button for an artifact."""
    query = update.callback_query
    user_id = str(query.from_user.id)
    chat_id = query.message.chat_id
    artifact_name = query.data.split("_")[1]

    # Check if the artifact has already been claimed
    artifact_data = context.chat_data.get(f"artifact_{artifact_name}")
    if not artifact_data or artifact_data.get("claimed", False):
        await query.answer("❌ This artifact has already been claimed.", show_alert=True)
        return

    # Mark the artifact as claimed
    artifact_data["claimed"] = True
    context.chat_data[f"artifact_{artifact_name}"] = artifact_data

    # Update user's bag with the artifact
    user_data = get_genshin_user_by_id(user_id)
    if not user_data:
        user_data = {
            "user_id": user_id,
            "primos": 16000,
            "bag": {"artifacts": {}},
            "daily_earned": 0,
            "last_reset": datetime.utcnow() + timedelta(hours=5, minutes=30),
        }

    if "artifacts" not in user_data["bag"]:
        user_data["bag"]["artifacts"] = {}

    if artifact_name not in user_data["bag"]["artifacts"]:
        user_data["bag"]["artifacts"][artifact_name] = {"image": ARTIFACTS[artifact_name], "count": 1}  # Initialize count
    else:
        user_data["bag"]["artifacts"][artifact_name]["count"] += 1  # Increment count

    save_genshin_user(user_data)

    await query.answer(f"🎉 You claimed the {artifact_name} (x{user_data['bag']['artifacts'][artifact_name]['count']})!", show_alert=True)

    # Delete the artifact reward message
    artifact_message_id = artifact_data.get("message_id")
    if artifact_message_id:
        await context.bot.delete_message(chat_id=chat_id, message_id=artifact_message_id)

def reset_artifact_claimed(context: CallbackContext) -> None:
    """Reset the claimed status of an artifact after a certain period."""
    job = context.job
    chat_id = job.chat_id
    artifact_name = job.name.replace("reset_", "")  
    if f"artifact_{artifact_name}" in context.chat_data:
        del context.chat_data[f"artifact_{artifact_name}"]
        logger.info(f"Current chat_data: {context.chat_data}")
        logger.info(f"Artifact {artifact_name} reset for chat {chat_id}.")


async def add_primos(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🔒 You don't have permission to use this command.")
        return
    # Ensure proper command format
    if len(context.args) < 2:
        await update.message.reply_text("❗ Usage: /add primo <user_id> <amount>")
        return
    user_id = context.args[0]
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❗ The amount must be a valid number.")
        return
    if amount <= 0:
        await update.message.reply_text("❗ The amount must be a positive number.")
        return
    user_data = get_genshin_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text(f"❗ User with ID {user_id} does not exist.")
        return
    user_data["primos"] = user_data.get("primos", 0) + amount
    save_genshin_user(user_data)
    await update.message.reply_text(f"✅ {amount} primogems have been added to user {user_id}'s account.")

BASE_5_STAR_RATE = 0.006  # Base chance for a 5-star item
GUARANTEED_5_STAR_PITY = 80  # Pulls needed for guaranteed 5-star
PULL_THRESHOLD = 10  # Pulls needed for guaranteed 4-star
COST_PER_PULL = 160  # 160 primogems per pull

def draw_item(characters: Dict[str, int], weapons: Dict[str, int], pull_counter: int, last_five_star_pull: int) -> Tuple[str, str, int]:
    # Determine if we should draw a 5-star item
    if pull_counter - last_five_star_pull >= GUARANTEED_5_STAR_PITY:
        item = draw_5_star_item(characters, weapons)
        # Reset pity counter after drawing a 5-star item
        return item, "characters" if item in characters else "weapons", 0

    # Check if we are due for a guaranteed 4-star item
    if pull_counter % PULL_THRESHOLD == 0 and pull_counter != 0:
        item = draw_4_star_item(characters, weapons)
        return item, "characters" if item in characters else "weapons", pull_counter + 1

    # Determine 5-star rate depending on pulls
    if pull_counter - last_five_star_pull >= GUARANTEED_5_STAR_PITY:
        five_star_chance = 1.0
    else:
        five_star_chance = BASE_5_STAR_RATE

    # Draw a 5-star item based on chance
    if random.random() < five_star_chance:
        item = draw_5_star_item(characters, weapons)
        # Reset pity counter after drawing a 5-star item
        return item, "characters" if item in characters else "weapons", 0

    # Draw a 4-star item if not a 5-star item
    if pull_counter % PULL_THRESHOLD == 0 and pull_counter != 0:
        item = draw_4_star_item(characters, weapons)
        return item, "characters" if item in characters else "weapons", pull_counter + 1

    # Otherwise, draw a 3-star item
    item = draw_3_star_item(characters, weapons)
    return item, "characters" if item in characters else "weapons", pull_counter + 1

def draw_5_star_item(characters: Dict[str, int], weapons: Dict[str, int]) -> str:
    five_star_items = list({k: v for k, v in {**characters, **weapons}.items() if v == 5}.keys())
    return random.choice(five_star_items)

def draw_4_star_item(characters: Dict[str, int], weapons: Dict[str, int]) -> str:
    four_star_items = list({k: v for k, v in {**characters, **weapons}.items() if v == 4}.keys())
    return random.choice(four_star_items)

def draw_3_star_item(characters: Dict[str, int], weapons: Dict[str, int]) -> str:
    three_star_items = list({k: v for k, v in {**characters, **weapons}.items() if v == 3}.keys())
    return random.choice(three_star_items)


def update_item(user_data: Dict, item: str, item_type: str):
    if item_type not in ["characters", "weapons"]:
        raise ValueError(f"Invalid item type: {item_type}")

    if item_type not in user_data["bag"]:
        user_data["bag"][item_type] = {}

    if item not in user_data["bag"][item_type]:
        if item_type == "characters":
            user_data["bag"][item_type][item] = "✨ C1"
        elif item_type == "weapons":
            user_data["bag"][item_type][item] = "⚔️ R1"
    else:
        current_count = user_data["bag"][item_type][item]
        if item_type == "characters":
            current_level = int(current_count.split('C')[1]) if 'C' in current_count else 1
            user_data["bag"][item_type][item] = f"✨ C{current_level + 1}"
        elif item_type == "weapons":
            current_level = int(current_count.split('R')[1]) if 'R' in current_count else 1
            user_data["bag"][item_type][item] = f"⚔️ R{current_level + 1}"
            
async def pull(update: Update, context: CallbackContext) -> None:
    """Handle the /pull command for Genshin Impact-style pulls."""
    user_id = str(update.effective_user.id)
    user_data = get_genshin_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("🔹 You need to start the bot first by using /start.")
        return

    try:
        number_of_pulls = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Usage: /pull <number> (1-10)")
        return

    if number_of_pulls < 1 or number_of_pulls > 10:
        await update.message.reply_text("❗ Please specify a number between 1 and 10.")
        return

    total_cost = number_of_pulls * COST_PER_PULL
    if user_data["primos"] < total_cost:
        await update.message.reply_text(f"❗ You do not have enough primogems. Needed: {total_cost}")
        return
    
    user_data["primos"] -= total_cost
    pull_counter = user_data.get('pull_counter', 0)
    last_five_star_pull = user_data.get('last_five_star_pull', 0)
    items_pulled = {"characters": [], "weapons": []}

    for _ in range(number_of_pulls):
        item, item_type, pity_reset = draw_item(CHARACTERS, WEAPONS, pull_counter, last_five_star_pull)
        items_pulled[item_type].append(item)
        update_item(user_data, item, item_type)
        pull_counter += 1
        if item_type == "characters" and CHARACTERS.get(item) == 5:
            last_five_star_pull = pull_counter
        
        # Update pity counter if needed
        if pity_reset == 0:
            last_five_star_pull = pull_counter

    user_data['pull_counter'] = pull_counter
    user_data['last_five_star_pull'] = last_five_star_pull
    save_genshin_user(user_data)

    characters_str = "\n".join([f"✨ {char} ({CHARACTERS[char]}★)" for char in items_pulled["characters"]]) if items_pulled["characters"] else "No characters pulled."
    weapons_str = "\n".join([f"⚔️ {weapon} ({WEAPONS[weapon]}★)" for weapon in items_pulled["weapons"]]) if items_pulled["weapons"] else "No weapons pulled."
    
    response = (
        "🔹 **Pull Results:**\n\n"
        f"{characters_str}\n"
        f"{weapons_str}\n\n"
        f"💎 **Remaining Primogems:** {user_data['primos']}"
    )
    await update.message.reply_text(response, parse_mode='Markdown')

async def bag(update: Update, context: CallbackContext) -> None:
    """Show user's bag contents."""
    user_id = str(update.effective_user.id)
    user_data = get_genshin_user_by_id(user_id) or {"bag": {}}
    
    if not user_data:
        await update.message.reply_text("🔹 You need to start the bot first by using /start.")
        return

    # Display the user's bag
    primos = user_data.get("primos", 0)
    characters = user_data["bag"].get("characters", {})
    weapons = user_data["bag"].get("weapons", {})
    artifacts = user_data["bag"].get("artifacts", {})

    # Total counts
    total_characters = sum(1 for _ in characters)
    total_weapons = sum(1 for _ in weapons)
    total_artifacts = sum(1 for _ in artifacts)

    # Generate the text for characters, weapons, and artifacts
    characters_str = "\n".join([f"✨ {char}: {info}" for char, info in characters.items()]) if characters else "No characters in bag."
    weapons_str = "\n".join([f"⚔️ {weapon}: {info}" for weapon, info in weapons.items()]) if weapons else "No weapons in bag."

    # Handle artifacts with backward compatibility for 'refinement' field
    artifacts_str = []
    for name, info in artifacts.items():
        if "count" in info:
            artifacts_str.append(f"🖼️ {name}: x{info['count']}")
        elif "refinement" in info:  # Backward compatibility for old 'refinement' field
            artifacts_str.append(f"🖼️ {name}: x{info['refinement']}")
        else:
            artifacts_str.append(f"🖼️ {name}: x1")  # Default to x1 if neither field exists
    artifacts_str = "\n".join(artifacts_str) if artifacts_str else "No artifacts in bag."

    keyboard = [
        [InlineKeyboardButton("Characters", callback_data="show_characters"),
         InlineKeyboardButton("Weapons", callback_data="show_weapons"),
         InlineKeyboardButton("Artifacts", callback_data="show_artifacts")],
        [InlineKeyboardButton("Back", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    response = (
        "🔹 **Your Bag:**\n\n"
        f"💎 **Primogems:** {primos}\n\n"
        f"👤 **Total Characters:** {total_characters}\n"
        f"⚔️ **Total Weapons:** {total_weapons}\n"
        f"🖼️ **Total Artifacts:** {total_artifacts}"
    )

    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

async def button(update: Update, context: CallbackContext) -> None:
    """Handle button presses related to Genshin Impact content."""    
    query = update.callback_query
    await query.answer()  # Answer the callback query to stop the loading animation
    
    user_id = str(query.from_user.id)
    user_data = get_genshin_user_by_id(user_id)
    if not user_data:
        await query.edit_message_text("❗ You need to start the bot first by using /start.")
        return

    if query.data == "show_characters":
        characters = user_data["bag"].get("characters", {})
        characters_str = "\n".join([f"✨ {char}: {info}" for char, info in characters.items()]) if characters else "No characters in bag."
        response = f"👤 **Characters:**\n{characters_str}"
        keyboard = [
            [InlineKeyboardButton("Weapons", callback_data="show_weapons"),
             InlineKeyboardButton("Artifacts", callback_data="show_artifacts")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
    elif query.data == "show_weapons":
        weapons = user_data["bag"].get("weapons", {})
        weapons_str = "\n".join([f"⚔️ {weapon}: {info}" for weapon, info in weapons.items()]) if weapons else "No weapons in bag."
        response = f"⚔️ **Weapons:**\n{weapons_str}"
        keyboard = [
            [InlineKeyboardButton("Characters", callback_data="show_characters"),
             InlineKeyboardButton("Artifacts", callback_data="show_artifacts")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
    elif query.data == "show_artifacts":
        artifacts = user_data["bag"].get("artifacts", {})
        # Handle artifacts with backward compatibility for 'refinement' field
        artifacts_str = []
        for name, info in artifacts.items():
            if "count" in info:
                artifacts_str.append(f"🖼️ {name}: x{info['count']}")
            elif "refinement" in info:  # Backward compatibility for old 'refinement' field
                artifacts_str.append(f"🖼️ {name}: x{info['refinement']}")
            else:
                artifacts_str.append(f"🖼️ {name}: x1")  # Default to x1 if neither field exists
        artifacts_str = "\n".join(artifacts_str) if artifacts_str else "No artifacts in bag."
        response = f"🖼️ **Artifacts:**\n{artifacts_str}"
        keyboard = [
            [InlineKeyboardButton("Characters", callback_data="show_characters"),
             InlineKeyboardButton("Weapons", callback_data="show_weapons")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
    elif query.data == "back":
        # Handle the "Back" button by showing the main bag view
        primos = user_data.get("primos", 0)
        characters = user_data["bag"].get("characters", {})
        weapons = user_data["bag"].get("weapons", {})
        artifacts = user_data["bag"].get("artifacts", {})

        total_characters = sum(1 for _ in characters)
        total_weapons = sum(1 for _ in weapons)
        total_artifacts = sum(1 for _ in artifacts)

        response = (
            "🔹 **Your Bag:**\n\n"
            f"💎 **Primogems:** {primos}\n\n"
            f"👤 **Total Characters:** {total_characters}\n"
            f"⚔️ **Total Weapons:** {total_weapons}\n"
            f"🖼️ **Total Artifacts:** {total_artifacts}"
        )
        
        keyboard = [
            [InlineKeyboardButton("Characters", callback_data="show_characters"),
             InlineKeyboardButton("Weapons", callback_data="show_weapons"),
             InlineKeyboardButton("Artifacts", callback_data="show_artifacts")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
    else:
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(response, parse_mode='Markdown', reply_markup=reply_markup)

def get_all_genshin_users():
    """
    Retrieve all Genshin users from the MongoDB collection.
    """    
    return list(genshin_collection.find({}, {"_id": 0, "user_id": 1, "primos": 1, "first_name": 1}))

async def primo_leaderboard(update: Update, context: CallbackContext) -> None:
    """Show the top 25 users by primogems."""
    # Get top 25 users by primogems
    top_users = genshin_collection.find().sort("primos", -1).limit(25)
    
    # Create leaderboard message
    leaderboard = "💎 <b>Primogems Leaderboard</b>\n\n"
    
    for i, user in enumerate(top_users, 1):
        # Try to get the name from different possible fields
        name = user.get('first_name') or user.get('username') or user.get('name')
        
        # If no name is found, try to get it from the user collection
        if not name:
            user_data = user_collection.find_one({"user_id": user.get('user_id')})
            if user_data:
                name = user_data.get('first_name') or user_data.get('username') or user_data.get('name')
        
        # If still no name, use a placeholder
        if not name:
            name = f"User {user.get('user_id', 'Unknown')}"
            
        primos = user.get('primos', 0)
        leaderboard += f"{i}. {name}: {primos:,} primogems\n"
    
    await update.message.reply_text(leaderboard, parse_mode='HTML')

async def reset_bag_data(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    if user_id != str(OWNER_ID):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    # Reset bag data only for the user who called the command
    genshin_collection.update_one({"user_id": user_id}, {"$set": {"bag": {}}})
    logger.info(f"Bag data reset for user {user_id}")
    await update.message.reply_text("Your bag data has been reset.")

async def drop_primos(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("Amount must be a positive number.")
            return
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /drop <amount> (e.g., /drop 100)")
        return

    try:
        genshin_collection.update_many({}, {"$inc": {"primos": amount}})
        logger.info(f"{amount} primos dropped to all users.")
        await update.message.reply_text(f"{amount} primos have been dropped to all users.")
    except Exception as e:
        logger.error(f"Error dropping primos: {e}")
        await update.message.reply_text("❌ An error occurred while dropping primos.")

def get_genshin_handlers():
    """Return list of handlers."""
    return [
        CommandHandler("pull", pull),
        CommandHandler("bag", bag),
        CommandHandler("primo_leaderboard", primo_leaderboard),
        CommandHandler("reset_bag", reset_bag_data),
        CommandHandler("drop_primos", drop_primos),
        CommandHandler("artifact_settings", artifact_settings),
        CommandHandler("set_threshold", set_threshold),
        CommandHandler("toggle_artifacts", toggle_artifacts),
        CallbackQueryHandler(button, pattern="^genshin_")
    ]

def initialize_user(user_id):
    user_data = {
        "primos": 16000,  # Changed from 0 to 16000
        "bag": [],
        "last_pull": None,
        "last_reward": None
    }
    user_collection.update_one({"user_id": user_id}, {"$setOnInsert": user_data}, upsert=True)
