from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext
import random
from pymongo import MongoClient
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple

OWNER_ID = 5667016949
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
user_collection = db["users"]
genshin_collection = db["genshin_users"]

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
            "bag": {},
            "daily_earned": 0,        # New field to track daily earned primogems
            "last_reset": today_5am,  # New field to track the last reset time
        }
        save_genshin_user(new_genshin_user)
        logger.info(f"Genshin user {user_id} initialized.")


async def reward_primos(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    user_data = get_genshin_user_by_id(user_id)

    # If the user doesn't exist, initialize their data
    if not user_data:
        user_data = {
            "user_id": user_id,
            "primos": 16000,  # Initial primogems
            "bag": {},
            "daily_earned": 0,
            "last_reset": datetime.utcnow() + timedelta(hours=5, minutes=30),  # IST time
        }
        save_genshin_user(user_data)

    # Add 5 primogems for each message
    user_data["primos"] += 5
    user_data["daily_earned"] += 5

    # Save the updated user data
    save_genshin_user(user_data)

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
    if item_type not in user_data["bag"]:
        user_data["bag"][item_type] = {}
    
    if item not in user_data["bag"][item_type]:
        if item_type == "characters":
            user_data["bag"][item_type][item] = "✨ C1"  # Start with Constellation C1
        elif item_type == "weapons":
            user_data["bag"][item_type][item] = "⚔️ R1"  # Start with Refinement R1
    else:
        current_count = user_data["bag"][item_type][item]
        if item_type == "characters":
            # Update constellation level
            if 'C' in current_count:
                current_level = int(current_count.split('C')[1])
                new_level = current_level + 1
                user_data["bag"][item_type][item] = f"✨ C{new_level}"
            else:
                user_data["bag"][item_type][item] = "✨ C2"  # Convert to C2 if initially missing
        elif item_type == "weapons":
            # Update refinement level
            if 'R' in current_count:
                current_level = int(current_count.split('R')[1])
                new_level = current_level + 1
                user_data["bag"][item_type][item] = f"⚔️ R{new_level}"
            else:
                user_data["bag"][item_type][item] = "⚔️ R2"

async def pull(update: Update, context: CallbackContext) -> None:
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
    user_id = str(update.effective_user.id)
    user_data = get_genshin_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("🔹 You need to start the bot first by using /start.")
        return

    primos = user_data.get("primos", 0)
    characters = user_data["bag"].get("characters", {})
    weapons = user_data["bag"].get("weapons", {})

    # Total counts
    total_characters = sum(1 for _ in characters)
    total_weapons = sum(1 for _ in weapons)

    # Generate the text for characters and weapons
    characters_str = "\n".join([f"✨ {char}: {info}" for char, info in characters.items()]) if characters else "No characters in bag."
    weapons_str = "\n".join([f"⚔️ {weapon}: {info}" for weapon, info in weapons.items()]) if weapons else "No weapons in bag."

    keyboard = [
        [InlineKeyboardButton("Characters", callback_data="show_characters"),
         InlineKeyboardButton("Weapons", callback_data="show_weapons")],
        [InlineKeyboardButton("Back", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    response = (
        "🔹 **Your Bag:**\n\n"
        f"💎 **Primogems:** {primos}\n\n"
        f"👤 **Total Characters:** {total_characters}\n"
        f"⚔️ **Total Weapons:** {total_weapons}"
    )

    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')


async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

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
            [InlineKeyboardButton("Weapons", callback_data="show_weapons")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
    elif query.data == "show_weapons":
        weapons = user_data["bag"].get("weapons", {})
        weapons_str = "\n".join([f"⚔️ {weapon}: {info}" for weapon, info in weapons.items()]) if weapons else "No weapons in bag."
        response = f"⚔️ **Weapons:**\n{weapons_str}"
        keyboard = [
            [InlineKeyboardButton("Characters", callback_data="show_characters")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
    elif query.data == "back":
        # Correctly handle the "Back" button by using the existing `query` to update the message
        primos = user_data.get("primos", 0)
        characters = user_data["bag"].get("characters", {})
        weapons = user_data["bag"].get("weapons", {})

        total_characters = sum(1 for _ in characters)
        total_weapons = sum(1 for _ in weapons)

        characters_str = "\n".join([f"✨ {char}: {info}" for char, info in characters.items()]) if characters else "No characters in bag."
        weapons_str = "\n".join([f"⚔️ {weapon}: {info}" for weapon, info in weapons.items()]) if weapons else "No weapons in bag."

        keyboard = [
            [InlineKeyboardButton("Characters", callback_data="show_characters"),
             InlineKeyboardButton("Weapons", callback_data="show_weapons")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        response = (
            "🔹 **Your Bag:**\n\n"
            f"💎 **Primogems:** {primos}\n\n"
            f"👤 **Total Characters:** {total_characters}\n"
            f"⚔️ **Total Weapons:** {total_weapons}"
        )

        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        return
    else:
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(response, parse_mode='Markdown', reply_markup=reply_markup)

def get_all_genshin_users():
    """
    Retrieve all Genshin users from the MongoDB collection.
    """
    return list(genshin_collection.find({}, {"_id": 0, "user_id": 1, "primos": 1, "first_name": 1}))

async def leaderboard(update: Update, context: CallbackContext) -> None:
    users = get_all_genshin_users()
    
    if not users:
        await update.message.reply_text("❗ No users found.")
        return

    # Sort users by primos in descending order
    users.sort(key=lambda x: x.get("primos", 0), reverse=True)

    # Create the leaderboard message
    leaderboard_message = "🔹 **Leaderboard:**\n\n"
    for idx, user in enumerate(users[:10]):  # Top 10 users
        first_name = user.get('first_name', 'Unknown')  # Default to 'Unknown' if no name
        primogems = user.get('primos', 0)
        leaderboard_message += (
            f"{idx + 1}. 🏆 {first_name} - **{primogems}** Primogems\n"
        )

    await update.message.reply_text(leaderboard_message, parse_mode='Markdown')

def handle_message(update, context):
    chat_id = update.effective_chat.id
    message_counts[chat_id] = message_counts.get(chat_id, 0) + 1
    if message_counts[chat_id] % 100 == 0:
        send_reward(update, context)

async def reset_bag_data(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    # Reset bag data for all users
    genshin_collection.update_many({}, {"$set": {"bag": {}}})
    logger.info("Bag data reset for all users.")
    await update.message.reply_text("Bag data has been reset for all users.")

# Function to drop primos to all users
async def drop_primos(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Please specify a valid number of primos to drop. Usage: /drop <amount>")
        return

    # Add the specified amount of primos to all users
    genshin_collection.update_many({}, {"$inc": {"primos": amount}})
    logger.info(f"{amount} primos dropped to all users.")
    await update.message.reply_text(f"{amount} primos have been dropped to all users.")

