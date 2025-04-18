from pymongo import MongoClient
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from datetime import datetime, timedelta
import time
import pytz
import asyncio
from functools import lru_cache

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("Multiplayer")

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
user_collection = db['users']
game_collection = db["multiplayer_games"]

multiplayer_games = {}
games_lock = asyncio.Lock()

# Ensure UTC timezone is used consistently
def get_current_utc_time():
    return datetime.now(pytz.utc)

# Function to get user first name
async def get_user_name_cached(user_id, context):
    try:
        user = await context.bot.get_chat(user_id)
        return user.first_name if user.first_name else f"Player {user_id}"
    except Exception as e:
        logger.error(f"Error getting user name for {user_id}: {e}")
        return f"Player {user_id}"

# Shared game state reference
multiplayer_games = multiplayer_games

# Update last_move on every interaction
async def update_last_move(playing_id: str):
    current_time = get_current_utc_time()
    try:
        game_collection.update_one(
            {"playing_id": playing_id},
            {"$set": {"last_move": current_time}}
        )
        async with games_lock:
            if playing_id in multiplayer_games:
                multiplayer_games[playing_id]["last_move"] = current_time
        logger.info(f"Updated last_move for game {playing_id} to {current_time}")
    except Exception as e:
        logger.error(f"Error updating last_move for game {playing_id}: {e}")

async def check_user_started_bot(update: Update, context: CallbackContext) -> bool:
    query = update.callback_query
    user = update.effective_user
    user_id = str(user.id)
    user_data = user_collection.find_one({"user_id": user_id})

    if not user_data:
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("🎮 Open Cricket Game", url=f"https://t.me/{bot_username}")]]
        user_tag = f"@{user.username}" if user.username else user.first_name if user.first_name else user_id

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ {user_tag}, you need to start the bot first!\n"
                 f"Click the button below to start the bot.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return False
    return True

async def get_game_data(playing_id: str) -> dict:
    playing_id = str(playing_id)
    if playing_id in multiplayer_games:
        return multiplayer_games[playing_id]
    # Try to load from DB
    game_data = game_collection.find_one({"playing_id": playing_id})
    if game_data:
        game = {k: v for k, v in game_data.items() if k != "_id"}
        async with games_lock:
            multiplayer_games[playing_id] = game
        return game
    return None

async def multiplayer(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    if update.effective_chat.type == "private":
        await context.bot.send_message(chat_id=chat_id, text="⚠️ This command can only be used in group chats!")
        return

    if not await check_user_started_bot(update, context):
        return

    max_overs = 5
    max_wickets = 5

    if context.args:
        try:
            if len(context.args) >= 1:
                max_overs = int(context.args[0])
            if len(context.args) >= 2:
                max_wickets = int(context.args[1])
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Invalid format! Use: /multiplayer [overs] [wickets]")
            return

    playing_id = str(chat_id)
    game_data = {
        "playing_id": playing_id,
        "batters": [],
        "bowlers": [],
        "max_overs": max_overs,
        "max_wickets": max_wickets,
        "group_chat_id": chat_id,
        "status": "waiting",
        "message_id": None,
        "last_move": get_current_utc_time(),
        "start_time": None,
        "admin_id": user.id,
        "batter_choice": None,
        "bowler_choice": None,
        "score": 0,
        "wickets": 0,
        "over": 0,
        "ball": 0,
        "innings": 1,
        "last_action": get_current_utc_time(),
        "batter_stats": {},
        "bowler_stats": {}
    }

    logger.info(f"[multiplayer] Creating new game with ID: {playing_id}")
    async with games_lock:
        multiplayer_games[playing_id] = game_data

    game_collection.update_one({"playing_id": playing_id}, {"$set": game_data}, upsert=True)

    desc = f"🏏 *Cricket Match Started!*\n\nFormat: {max_overs} over{'s' if max_overs > 1 else ''}, {max_wickets} wicket{'s' if max_wickets > 1 else ''}\n\n"
    desc += "• Join as Batter or Bowler\n• Match will start once teams are full."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
    ])

    sent_message = await context.bot.send_message(chat_id=chat_id, text=desc, reply_markup=keyboard, parse_mode="Markdown")

    game_data["message_id"] = sent_message.message_id
    async with games_lock:
        multiplayer_games[playing_id]["message_id"] = sent_message.message_id
    game_collection.update_one({"playing_id": playing_id}, {"$set": {"message_id": sent_message.message_id}})

    logger.info(f"[multiplayer] Game created and message_id stored: {sent_message.message_id}")

async def MButton_join(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    try:
        _, role, playing_id = query.data.split('_', 2)
    except ValueError:
        await query.answer("Invalid callback!")
        return

    if not await check_user_started_bot(update, context):
        await query.answer("Start the bot first!")
        return

    game = await get_game_data(playing_id)
    if not game:
        await query.answer("Game not found or expired!")
        return

    if game["status"] not in ["waiting", "ready"]:
        await query.answer("Game already started!")
        return

    user_id = int(user_id)
    
    if user_id in game["batters"] or user_id in game["bowlers"]:
        await query.answer("You're already in the game!")
        return

    if role == "batter":
        if len(game["batters"]) >= game["max_wickets"]:
            await query.answer("Batter team is full!")
            return
        game["batters"].append(user_id)
    else:
        if len(game["bowlers"]) >= game["max_wickets"]:
            await query.answer("Bowler team is full!")
            return
        game["bowlers"].append(user_id)

    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one({"playing_id": playing_id}, {"$set": {"batters": game["batters"], "bowlers": game["bowlers"]}})

    batter_names = []
    for uid in game["batters"]:
        try:
            name = await get_user_name_cached(uid, context)
            batter_names.append(name)
        except:
            batter_names.append(f"Player {uid}")
    
    bowler_names = []
    for uid in game["bowlers"]:
        try:
            name = await get_user_name_cached(uid, context)
            bowler_names.append(name)
        except:
            bowler_names.append(f"Player {uid}")

    text = f"👥 *Current Players*\n\n"
    text += f"▶️ Batters ({len(batter_names)}/{game['max_wickets']}): {', '.join(batter_names) if batter_names else 'None'}\n"
    text += f"▶️ Bowlers ({len(bowler_names)}/{game['max_wickets']}): {', '.join(bowler_names) if bowler_names else 'None'}\n\n"
    
    if game["status"] == "waiting":
        text += f"Match starts when both sides are full."
    elif game["status"] == "ready":
        time_left = (game["start_time"] - datetime.now(pytz.utc)).total_seconds()
        if time_left > 15:
            text += f"Game will start in {int(time_left)} seconds..."
        elif time_left > 10:
            text += "Game will start in 15 seconds..."
        elif time_left > 5:
            text += "Game will start in 10 seconds..."
        else:
            text += "Game starting in 5 seconds..."
    else:
        text += "Game is starting soon..."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
    ])

    try:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")
        await query.answer("You joined as " + role.capitalize())
    except Exception as e:
        logger.error(f"Edit error: {e}")

    if len(game["batters"]) >= game["max_wickets"] and len(game["bowlers"]) >= game["max_wickets"] and game["status"] == "waiting":
        game["status"] = "ready"
        game["start_time"] = datetime.now(pytz.utc) + timedelta(seconds=15)
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one({"playing_id": playing_id}, {"$set": {"status": "ready", "start_time": game["start_time"]}})
        asyncio.create_task(start_game_countdown(playing_id, context))

async def start_game_countdown(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game:
        return
    
    while True:
        now = datetime.now(pytz.utc)
        if game["start_time"] is None:
            break
            
        time_left = (game["start_time"] - now).total_seconds()
        
        if time_left <= 0:
            await start_game(playing_id, context)
            break
        elif 10 < time_left <= 15:
            if game.get("countdown_message") != "15":
                game_message = await context.bot.edit_message_text(
                    chat_id=game["group_chat_id"],
                    message_id=game["message_id"],
                    text=f"Game will start in 15 seconds...",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
                        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
                        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
                    ]),
                    parse_mode="Markdown"
                )
                game["message_id"] = game_message.message_id
                game["countdown_message"] = "15"
                async with games_lock:
                    multiplayer_games[playing_id] = game
                game_collection.update_one({"playing_id": playing_id}, {"$set": {"message_id": game_message.message_id}})
        elif 5 < time_left <= 10:
            if game.get("countdown_message") != "10":
                game_message = await context.bot.edit_message_text(
                    chat_id=game["group_chat_id"],
                    message_id=game["message_id"],
                    text="Game starting in 10 seconds...",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
                        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
                        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
                    ]),
                    parse_mode="Markdown"
                )
                game["message_id"] = game_message.message_id
                game["countdown_message"] = "10"
                async with games_lock:
                    multiplayer_games[playing_id] = game
                game_collection.update_one({"playing_id": playing_id}, {"$set": {"message_id": game_message.message_id}})
        elif time_left <= 5:
            if game.get("countdown_message") != "5":
                game_message = await context.bot.edit_message_text(
                    chat_id=game["group_chat_id"],
                    message_id=game["message_id"],
                    text="Game starting in 5 seconds...",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
                        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
                        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
                    ]),
                    parse_mode="Markdown"
                )
                game["message_id"] = game_message.message_id
                game["countdown_message"] = "5"
                async with games_lock:
                    multiplayer_games[playing_id] = game
                game_collection.update_one({"playing_id": playing_id}, {"$set": {"message_id": game_message.message_id}})
        
        await asyncio.sleep(1)

async def Mhandle_remove_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, playing_id = query.data.split('_', 1)
    
    if not await check_user_started_bot(update, context):
        await query.answer("You need to start the bot first!")
        return
    
    game = await get_game_data(playing_id)
    if not game:
        await query.answer("Game not found or expired!")
        await query.edit_message_text(
            text="This game has expired or been deleted. Start a new game with /multiplayer command.",
            reply_markup=None
        )
        return
    
    if game["status"] not in ["waiting", "ready"]:
        await query.answer("Game has already started!")
        return
    
    user_id = int(user_id)
    
    was_removed = False
    if user_id in game["batters"]:
        game["batters"].remove(user_id)
        was_removed = True
    elif user_id in game["bowlers"]:
        game["bowlers"].remove(user_id)
        was_removed = True
    
    if not was_removed:
        await query.answer("You're not part of this game!")
        return
    
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one(
        {"playing_id": playing_id},
        {"$set": {
            "batters": game["batters"],
            "bowlers": game["bowlers"]
        }}
    )
    
    batter_names = []
    for uid in game["batters"]:
        try:
            name = await get_user_name_cached(uid, context)
            batter_names.append(name)
        except:
            batter_names.append(f"Player {uid}")
    
    bowler_names = []
    for uid in game["bowlers"]:
        try:
            name = await get_user_name_cached(uid, context)
            bowler_names.append(name)
        except:
            bowler_names.append(f"Player {uid}")
    
    text = f"👥 *Current Players*\n\n"
    text += f"▶️ Batters ({len(batter_names)}/{game['max_wickets']}): {', '.join(batter_names) if batter_names else 'None'}\n"
    text += f"▶️ Bowlers ({len(bowler_names)}/{game['max_wickets']}): {', '.join(bowler_names) if bowler_names else 'None'}\n\n"
    
    if game["status"] == "waiting":
        text += f"Match starts when both sides are full."
    elif game["status"] == "ready":
        time_left = (game["start_time"] - datetime.now(pytz.utc)).total_seconds()
        if time_left > 15:
            text += f"Game will start in {int(time_left)} seconds..."
        elif time_left > 10:
            text += "Game will start in 15 seconds..."
        elif time_left > 5:
            text += "Game will start in 10 seconds..."
        else:
            text += "Game starting in 5 seconds..."
    else:
        text += "Game is starting soon..."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
    ])

    try:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")
        await query.answer("Removed successfully!")
    except Exception as e:
        logger.error(f"Edit error: {e}")

    if len(game["batters"]) >= game["max_wickets"] and len(game["bowlers"]) >= game["max_wickets"] and game["status"] == "waiting":
        game["status"] = "ready"
        game["start_time"] = datetime.now(pytz.utc) + timedelta(seconds=15)
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one({"playing_id": playing_id}, {"$set": {"status": "ready", "start_time": game["start_time"]}})
        asyncio.create_task(start_game_countdown(playing_id, context))

async def start_game(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game:
        return
    
    try:
        await context.bot.edit_message_text(
            chat_id=game["group_chat_id"],
            message_id=game["message_id"],
            text=f"🏏 *Cricket Tournament Started!*\n\n"
                f"Format: {game['max_overs']} over{'s' if game['max_overs'] > 1 else ''}, "
                f"{game['max_wickets']} wicket{'s' if game['max_wickets'] > 1 else ''}\n\n"
                f"Game is now in progress! Check your DMs from the bot to play.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error updating group message: {e}")
    
    # Initialize player messages dict
    game["player_messages"] = {}
    
    # Send initial notification message to all players
    for user_id in game["batters"] + game["bowlers"]:
        try:
            message = await context.bot.send_message(
                chat_id=user_id,
                text="🎮 Game has started! You are part of the tournament.\n\n"
                    "Wait for your turn to bat or bowl."
            )
            # Store message ID
            game["player_messages"][str(user_id)] = message.message_id
        except Exception as e:
            logger.error(f"Error notifying player {user_id}: {e}")
    
    game["status"] = "started"
    game["current_batter"] = game["batters"][0] if game["batters"] else None
    game["current_bowler"] = game["bowlers"][0] if game["bowlers"] else None
    game["batter_choice"] = None
    game["bowler_choice"] = None
    game["score"] = 0
    game["wickets"] = 0
    game["over"] = 0
    game["ball"] = 0
    game["innings"] = 1
    game["last_action"] = datetime.now(pytz.utc)
    
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one(
        {"playing_id": playing_id},
        {"$set": {
            "status": game["status"],
            "current_batter": game["current_batter"],
            "current_bowler": game["current_bowler"],
            "batter_choice": game["batter_choice"],
            "bowler_choice": game["bowler_choice"],
            "score": game["score"],
            "wickets": game["wickets"],
            "over": game["over"],
            "ball": game["ball"],
            "innings": game["innings"],
            "last_action": game["last_action"],
            "player_messages": game["player_messages"]
        }}
    )
    
    asyncio.create_task(game_timeout_checker(playing_id, context))
    await update_game_interface(playing_id, context)

async def game_timeout_checker(playing_id: str, context: CallbackContext):
    game = await get_game_data(playing_id)
    if not game:
        return
    
    while game["status"] == "started":
        now = datetime.now(pytz.utc)
        elapsed = (now - game["last_action"]).total_seconds()
        
        if elapsed > 15:
            if game["current_batter"] and game["current_batter"] in game["batters"]:
                game["batters"].remove(game["current_batter"])
                game["batters"].append(game["current_batter"])
                game["current_batter"] = game["batters"][0] if game["batters"] else None
                try:
                    await context.bot.edit_message_text(
                        chat_id=game["group_chat_id"],
                        message_id=game["message_id"],
                        text=f"Batter {await get_user_name_cached(game['current_batter'], context)} timed out! Next batter is up.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
            elif game["current_bowler"] and game["current_bowler"] in game["bowlers"]:
                game["bowlers"].remove(game["current_bowler"])
                game["bowlers"].append(game["current_bowler"])
                game["current_bowler"] = game["bowlers"][0] if game["bowlers"] else None
                try:
                    await context.bot.edit_message_text(
                        chat_id=game["group_chat_id"],
                        message_id=game["message_id"],
                        text=f"Bowler {await get_user_name_cached(game['current_bowler'], context)} timed out! Next bowler is up.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
            
            game["last_action"] = datetime.now(pytz.utc)
            async with games_lock:
                multiplayer_games[playing_id] = game
            game_collection.update_one({"playing_id": playing_id}, {"$set": game})
            await update_game_interface(playing_id, context)
        
        await asyncio.sleep(1)
        game = await get_game_data(playing_id)

async def update_game_interface(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when updating interface")
        return
    
    game["batter_choice"] = None
    game["bowler_choice"] = None
    game["last_action"] = datetime.now(pytz.utc)
    
    # Initialize player_messages dict if not exists
    if "player_messages" not in game:
        game["player_messages"] = {}
    
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one(
        {"playing_id": playing_id},
        {"$set": {
            "batter_choice": None,
            "bowler_choice": None,
            "last_action": game["last_action"],
            "player_messages": game.get("player_messages", {})
        }}
    )
    
    batter_id = game["current_batter"]
    bowler_id = game["current_bowler"]
    
    status_text = f"🏏 *Cricket Tournament - {'1st' if game['innings'] == 1 else '2nd'} Innings*\n\n"
    status_text += f"⏳ Over: {game['over']}.{game['ball']}\n"
    status_text += f"📊 Score: {game['score']}/{game['wickets']}\n"
    
    if game["innings"] == 2 and game.get("target"):
        status_text += f"🎯 Target: {game['target']} runs\n"
        status_text += f"💯 Need {game['target'] - game['score']} more runs\n\n"
    else:
        status_text += "\n"
    
    batter_keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"Mplay_{playing_id}|{i}"))
        if len(row) == 3:
            batter_keyboard.append(row)
            row = []
    
    bowler_keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"Mplay_{playing_id}|{i}"))
        if len(row) == 3:
            bowler_keyboard.append(row)
            row = []
    
    for user_id in game["batters"] + game["bowlers"]:
        user_id_str = str(user_id)
        try:
            if user_id == batter_id:
                message_text = status_text + f"🔸 Your turn to bat! Choose a number (1-6):"
                markup = InlineKeyboardMarkup(batter_keyboard)
            elif user_id == bowler_id:
                message_text = status_text + f"🔹 Your turn to bowl! Choose a number (1-6):"
                markup = InlineKeyboardMarkup(bowler_keyboard)
            else:
                message_text = status_text + f"⌛ Waiting for batter and bowler to play..."
                markup = None
                
            # If we have a message ID for this user, edit it
            if user_id_str in game["player_messages"]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=game["player_messages"][user_id_str],
                        text=message_text,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error editing message for user {user_id}: {e}")
                    # Message might have been deleted, send a new one
                    message = await context.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                    game["player_messages"][user_id_str] = message.message_id
            else:
                # Send a new message and store the ID
                message = await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                game["player_messages"][user_id_str] = message.message_id
            
        except Exception as e:
            logger.error(f"Error sending interface to {user_id}: {e}")
    
    # Update player_messages in DB and memory
    async with games_lock:
        multiplayer_games[playing_id]["player_messages"] = game["player_messages"]
    game_collection.update_one(
        {"playing_id": playing_id},
        {"$set": {"player_messages": game["player_messages"]}}
    )

async def Mhandle_play_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        parts = query.data.split('_', 1)
        if len(parts) != 2:
            await query.answer("Invalid game data")
            return
            
        game_parts = parts[1].split('|')
        if len(game_parts) != 2:
            await query.answer("Invalid game data")
            return
            
        playing_id = game_parts[0]
        number = int(game_parts[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing play data: {e}, data: {query.data}")
        await query.answer("Invalid game data")
        return
    
    user_id = int(user_id)
    
    game = await get_game_data(playing_id)
    if not game:
        await query.answer("Game not found or expired!")
        return
    
    if game["status"] != "started":
        await query.answer("This game is not active!")
        return
    
    if user_id != game.get("current_batter") and user_id != game.get("current_bowler"):
        await query.answer("It's not your turn!")
        return
    
    game["last_action"] = datetime.now(pytz.utc)
    await update_last_move(playing_id)

    if user_id == game.get("current_batter"):
        if game.get("batter_choice") is not None:
            await query.answer("You've already made your choice!")
            return
            
        game["batter_choice"] = number
        
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one(
            {"playing_id": playing_id},
            {"$set": {"batter_choice": number, "last_action": game["last_action"]}}
        )
        
        await query.answer(f"Your choice: {number}")
        
        if game.get("bowler_choice") is not None:
            await process_ball_result(playing_id, context)
    
    elif user_id == game.get("current_bowler"):
        if game.get("bowler_choice") is not None:
            await query.answer("You've already made your choice!")
            return
            
        game["bowler_choice"] = number
        
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one(
            {"playing_id": playing_id},
            {"$set": {"bowler_choice": number, "last_action": game["last_action"]}}
        )
        
        await query.answer(f"Your choice: {number}")
        
        if game.get("batter_choice") is not None:
            await process_ball_result(playing_id, context)

async def process_ball_result(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when processing ball result")
        return
    
    batter_choice = game.get("batter_choice")
    bowler_choice = game.get("bowler_choice")

    if batter_choice is None or bowler_choice is None:
        logger.error(f"Missing choices for game {playing_id}: batter={batter_choice}, bowler={bowler_choice}")
        return
    
    result_text = (
        f"🏏 *Ball Result*\n\n"
        f"Batter chose: {batter_choice}\n"
        f"Bowler chose: {bowler_choice}\n\n"
    )
    
    status_text = f"🏏 *Cricket Tournament - {'1st' if game['innings'] == 1 else '2nd'} Innings*\n\n"
    status_text += f"⏳ Over: {game['over']}.{game['ball']}\n"
    status_text += f"📊 Score: {game['score']}/{game['wickets']}\n"
    
    if game["innings"] == 2 and game.get("target"):
        status_text += f"🎯 Target: {game['target']} runs\n"
        status_text += f"💯 Need {game['target'] - game['score']} more runs\n\n"
    else:
        status_text += "\n"
    
    if batter_choice == bowler_choice:
        result_text += f"🎯 OUT! Batter is dismissed!"
        game["wickets"] += 1
        
        # Update bowler stats
        bowler_id = game["current_bowler"]
        if str(bowler_id) not in game["bowler_stats"]:
            game["bowler_stats"][str(bowler_id)] = {"wickets": 0, "runs": 0}
        game["bowler_stats"][str(bowler_id)]["wickets"] += 1
        
        for user_id in game["batters"] + game["bowlers"]:
            user_id_str = str(user_id)
            try:
                if user_id_str in game.get("player_messages", {}):
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=game["player_messages"][user_id_str],
                        text=status_text + result_text,
                        parse_mode="Markdown"
                    )
                else:
                    message = await context.bot.send_message(
                        chat_id=user_id,
                        text=status_text + result_text,
                        parse_mode="Markdown"
                    )
                    if "player_messages" not in game:
                        game["player_messages"] = {}
                    game["player_messages"][user_id_str] = message.message_id
            except Exception as e:
                logger.error(f"Error sending result to {user_id}: {e}")
        
        game["ball"] += 1
        if game["ball"] == 6:
            game["over"] += 1
            game["ball"] = 0
        
        if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
            async with games_lock:
                multiplayer_games[playing_id] = game
            game_collection.update_one(
                {"playing_id": playing_id},
                {"$set": {
                    "wickets": game["wickets"],
                    "over": game["over"],
                    "ball": game["ball"],
                    "last_action": game["last_action"],
                    "player_messages": game.get("player_messages", {}),
                    "bowler_stats": game["bowler_stats"]
                }}
            )
            await end_innings(playing_id, context)
            return
        
        current_batter = game["current_batter"]
        if current_batter in game["batters"]:
            game["batters"].remove(current_batter)
            game["batters"].append(current_batter)
            game["current_batter"] = game["batters"][0] if game["batters"] else None
        
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one(
            {"playing_id": playing_id},
            {"$set": {
                "wickets": game["wickets"],
                "over": game["over"],
                "ball": game["ball"],
                "current_batter": game["current_batter"],
                "batters": game["batters"],
                "last_action": game["last_action"],
                "player_messages": game.get("player_messages", {}),
                "bowler_stats": game["bowler_stats"]
            }}
        )
    else:
        runs = batter_choice
        result_text += f"💥 {runs} run{'s' if runs > 1 else ''} scored!"
        game["score"] += runs
        
        # Update batter stats
        batter_id = game["current_batter"]
        if str(batter_id) not in game["batter_stats"]:
            game["batter_stats"][str(batter_id)] = {"runs": 0}
        game["batter_stats"][str(batter_id)]["runs"] += runs
        
        for user_id in game["batters"] + game["bowlers"]:
            user_id_str = str(user_id)
            try:
                if user_id_str in game.get("player_messages", {}):
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=game["player_messages"][user_id_str],
                        text=status_text + result_text,
                        parse_mode="Markdown"
                    )
                else:
                    message = await context.bot.send_message(
                        chat_id=user_id,
                        text=status_text + result_text,
                        parse_mode="Markdown"
                    )
                    if "player_messages" not in game:
                        game["player_messages"] = {}
                    game["player_messages"][user_id_str] = message.message_id
            except Exception as e:
                logger.error(f"Error sending result to {user_id}: {e}")
        
        if game["innings"] == 2 and game.get("target") and game["score"] >= game["target"]:                    
            async with games_lock:
                multiplayer_games[playing_id] = game
            game_collection.update_one(
                {"playing_id": playing_id},
                {"$set": {
                    "score": game["score"], 
                    "last_action": game["last_action"],
                    "player_messages": game.get("player_messages", {}),
                    "batter_stats": game["batter_stats"]
                }}
            )
            
            await end_innings(playing_id, context)
            return
        
        game["ball"] += 1
        if game["ball"] == 6:
            game["over"] += 1
            game["ball"] = 0
            
            current_bowler = game["current_bowler"]
            if current_bowler in game["bowlers"]:
                game["bowlers"].remove(current_bowler)
                game["bowlers"].append(current_bowler)
                game["current_bowler"] = game["bowlers"][0] if game["bowlers"] else None
        
        if game["over"] >= game["max_overs"]:
            async with games_lock:
                multiplayer_games[playing_id] = game
            game_collection.update_one(
                {"playing_id": playing_id},
                {"$set": {
                    "score": game["score"],
                    "over": game["over"],
                    "ball": game["ball"],
                    "current_bowler": game["current_bowler"],
                    "bowlers": game["bowlers"],
                    "last_action": game["last_action"],
                    "player_messages": game.get("player_messages", {}),
                    "batter_stats": game["batter_stats"]
                }}
            )
            
            await end_innings(playing_id, context)
            return
        
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one(
            {"playing_id": playing_id},
            {"$set": {
                "score": game["score"],
                "over": game["over"],
                "ball": game["ball"],
                "current_bowler": game["current_bowler"],
                "bowlers": game["bowlers"],
                "last_action": game["last_action"],
                "player_messages": game.get("player_messages", {}),
                "batter_stats": game["batter_stats"]
            }}
        )
    
    # Wait a few seconds to let users read the result before updating the interface
    await asyncio.sleep(0.5)
    await update_game_interface(playing_id, context)

async def end_innings(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when ending innings")
        return
    
    if game["innings"] == 1:
        first_innings_score = game["score"]
        game["target"] = game["score"] + 1
        game["innings"] = 2
        game["score"] = 0
        game["over"] = 0
        game["ball"] = 0
        game["wickets"] = 0
        game["batters"], game["bowlers"] = game["bowlers"], game["batters"]
        game["current_batter"] = game["batters"][0] if game["batters"] else None
        game["current_bowler"] = game["bowlers"][0] if game["bowlers"] else None
        game["last_action"] = datetime.now(pytz.utc)
        
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one(
            {"playing_id": playing_id},
            {"$set": {
                "innings": game["innings"],
                "target": game["target"],
                "score": game["score"],
                "over": game["over"],
                "ball": game["ball"],
                "wickets": game["wickets"],
                "batters": game["batters"],
                "bowlers": game["bowlers"],
                "current_batter": game["current_batter"],
                "current_bowler": game["current_bowler"],
                "last_action": game["last_action"]
            }}
        )
        
        innings_message = (
            f"🏏 *First Innings Completed!*\n\n"
            f"First Innings Score: {first_innings_score}/{game['max_wickets']}\n"
            f"Second Innings Target: {game['target']} runs\n\n"
            f"Roles have been swapped. Game will continue shortly."
        )
        
        # Update all player messages
        for user_id in game["batters"] + game["bowlers"]:
            user_id_str = str(user_id)
            try:
                if user_id_str in game.get("player_messages", {}):
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=game["player_messages"][user_id_str],
                        text=innings_message,
                        parse_mode="Markdown"
                    )
                else:
                    message = await context.bot.send_message(
                        chat_id=user_id,
                        text=innings_message,
                        parse_mode="Markdown"
                    )
                    if "player_messages" not in game:
                        game["player_messages"] = {}
                    game["player_messages"][user_id_str] = message.message_id
            except Exception as e:
                logger.error(f"Error notifying player {user_id}: {e}")
        
        # Wait a few seconds before updating the interface
        await asyncio.sleep(3)
        await update_game_interface(playing_id, context)
    else:
        await declare_winner(playing_id, context)

async def declare_winner(playing_id: str, context: CallbackContext, innings_result=None) -> None:
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when declaring winner")
        return
    
    target = game.get("target", 0)
    first_innings_score = target - 1 if target else 0
    second_innings_score = game["score"]
    
    # Determine team names based on innings
    team_a = "Team A" if game["innings"] == 2 else "Team B"
    team_b = "Team B" if game["innings"] == 2 else "Team A"
    
    # Get player names for both teams
    team_a_players = []
    for uid in game["batters"] if game["innings"] == 2 else game["bowlers"]:
        try:
            name = await get_user_name_cached(uid, context)
            team_a_players.append(name)
        except:
            team_a_players.append(f"Player {uid}")
    
    team_b_players = []
    for uid in game["bowlers"] if game["innings"] == 2 else game["batters"]:
        try:
            name = await get_user_name_cached(uid, context)
            team_b_players.append(name)
        except:
            team_b_players.append(f"Player {uid}")
    
    if game["innings"] == 2:
        if second_innings_score >= target:
            winner = team_b
            if game["wickets"] < game["max_wickets"]:
                margin = f"by {game['max_wickets'] - game['wickets']} wickets"
            else:
                margin = "by last wicket"
        else:
            winner = team_a
            margin = f"by {target - second_innings_score - 1} runs"
    else:
        winner = "No winner"
        margin = "Game ended early"
    
    # Format player lists
    team_a_text = "\n".join([f"- {name}" for name in team_a_players]) if team_a_players else "None"
    team_b_text = "\n".join([f"- {name}" for name in team_b_players]) if team_b_players else "None"
    
    # Prepare detailed statistics
    batter_stats_text = ""
    if game.get("batter_stats"):
        batter_stats_text += "\n*Batter Stats:*\n"
        for player_id, stats in game["batter_stats"].items():
            player_name = await get_user_name_cached(int(player_id), context)
            batter_stats_text += f"{player_name}: {stats['runs']} runs\n"
    
    bowler_stats_text = ""
    if game.get("bowler_stats"):
        bowler_stats_text += "\n*Bowler Stats:*\n"
        for player_id, stats in game["bowler_stats"].items():
            player_name = await get_user_name_cached(int(player_id), context)
            bowler_stats_text += f"{player_name}: {stats['wickets']} wickets\n"
    
    result_message = innings_result if innings_result else ""
    result_message += (
        f"🏆 *GAME OVER!*\n\n"
        f"First Innings ({team_a}):\n{team_a_text}\n\n"
        f"Second Innings ({team_b}):\n{team_b_text}\n\n"
        f"Final Scores:\n"
        f"{team_a}: {first_innings_score} runs\n"
        f"{team_b}: {second_innings_score} runs\n\n"
        f"{batter_stats_text}"
        f"{bowler_stats_text}"
        f"🏆 {winner} won {margin}!\n"
    )
    
    try:
        # Edit the existing message in the group chat
        await context.bot.edit_message_text(
            chat_id=game["group_chat_id"],
            message_id=game["message_id"],
            text=result_message,
            parse_mode="Markdown"
        )

        try:
            await context.bot.unpin_chat_message(
                chat_id=game["group_chat_id"],
                message_id=game["message_id"]
            )
        except Exception as e:
            logger.error(f"Error unpinning message: {e}")
            
    except Exception as e:
        logger.error(f"Error sending result to group chat: {e}")

    # Update all player messages with the result
    for user_id in game["batters"] + game["bowlers"]:
        user_id_str = str(user_id)
        try:
            if user_id_str in game.get("player_messages", {}):
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=game["player_messages"][user_id_str],
                    text=result_message,
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=result_message,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error sending result to {user_id}: {e}")
    
    if playing_id in multiplayer_games:
        async with games_lock:
            del multiplayer_games[playing_id]
    
    game_collection.delete_one({"playing_id": playing_id})

async def Mhandle_cancel_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, playing_id = query.data.split('_', 1)
    
    game = await get_game_data(playing_id)
    if not game:
        await query.answer("Game not found or expired!")
        return
    
    if user_id != game["admin_id"]:
        await query.answer("Only the game admin can cancel the game!")
        return
    
    try:
        await context.bot.edit_message_text(
            chat_id=game["group_chat_id"],
            message_id=game["message_id"],
            text="🛑 Game cancelled by admin!",
            parse_mode="Markdown"
        )
        
        try:
            await context.bot.unpin_chat_message(
                chat_id=game["group_chat_id"],
                message_id=game["message_id"]
            )
        except Exception as e:
            logger.error(f"Error unpinning message: {e}")
            
    except Exception as e:
        logger.error(f"Error sending cancel notification: {e}")
    
    for uid in game["batters"] + game["bowlers"]:
        try:
            await context.bot.edit_message_text(
                chat_id=uid,
                message_id=game.get("player_message_id", uid),
                text="🛑 Game has been cancelled!"
            )
        except Exception as e:
            logger.error(f"Error notifying player {uid} about cancellation: {e}")
    
    if playing_id in multiplayer_games:
        async with games_lock:
            del multiplayer_games[playing_id]
    
    game_collection.delete_one({"playing_id": playing_id})
    
    await query.answer("Game cancelled!")

async def extend_time(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    playing_id = str(chat_id)
    
    game = await get_game_data(playing_id)
    if not game:
        await update.message.reply_text("No game found in this chat!")
        return
    
    if user.id != game["admin_id"]:
        await update.message.reply_text("Only the game admin can extend time!")
        return
    
    if game["status"] != "ready":
        await update.message.reply_text("Game is already started or not ready!")
        return
    
    game["start_time"] = game["start_time"] + timedelta(seconds=15)
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one({"playing_id": playing_id}, {"$set": {"start_time": game["start_time"]}})
    
    await context.bot.edit_message_text(
        chat_id=game["group_chat_id"],
        message_id=game["message_id"],
        text=f"Time extended! Game will start in {int((game['start_time'] - datetime.now(pytz.utc)).total_seconds())} seconds...",
        parse_mode="Markdown"
    )
    
    await update.message.delete()

async def stop_game(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    playing_id = str(chat_id)
    
    game = await get_game_data(playing_id)
    if not game:
        await update.message.reply_text("No game found in this chat!")
        return
    
    if user.id != game["admin_id"]:
        await update.message.reply_text("Only the game admin can stop the game!")
        return
    
    try:
        await context.bot.edit_message_text(
            chat_id=game["group_chat_id"],
            message_id=game["message_id"],
            text="🛑 Game stopped by admin!",
            parse_mode="Markdown"
        )
        
        try:
            await context.bot.unpin_chat_message(
                chat_id=game["group_chat_id"],
                message_id=game["message_id"]
            )
        except Exception as e:
            logger.error(f"Error unpinning message: {e}")
            
    except Exception as e:
        logger.error(f"Error sending stop notification: {e}")
    
    for uid in game["batters"] + game["bowlers"]:
        try:
            await context.bot.edit_message_text(
                chat_id=uid,
                message_id=game.get("player_message_id", uid),
                text="🛑 Game has been stopped by admin!"
            )
        except Exception as e:
            logger.error(f"Error notifying player {uid} about stop: {e}")
    
    if playing_id in multiplayer_games:
        async with games_lock:
            del multiplayer_games[playing_id]
    
    game_collection.delete_one({"playing_id": playing_id})
    
    await update.message.delete()

async def list_players(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playing_id = str(chat_id)
    
    game = await get_game_data(playing_id)
    if not game:
        await update.message.reply_text("No game found in this chat!")
        return
    
    batter_names = []
    for uid in game["batters"]:
        try:
            name = await get_user_name_cached(uid, context)
            batter_names.append(name)
        except:
            batter_names.append(f"Player {uid}")
    
    bowler_names = []
    for uid in game["bowlers"]:
        try:
            name = await get_user_name_cached(uid, context)
            bowler_names.append(name)
        except:
            bowler_names.append(f"Player {uid}")
    
    text = f"👥 *Current Players*\n\n"
    text += f"▶️ Batters ({len(batter_names)}/{game['max_wickets']}):\n"
    text += "\n".join([f"- {name}" for name in batter_names]) if batter_names else "None"
    text += f"\n\n▶️ Bowlers ({len(bowler_names)}/{game['max_wickets']}):\n"
    text += "\n".join([f"- {name}" for name in bowler_names]) if bowler_names else "None"
    
    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            message_id=game["message_id"],
            text=text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error updating player list: {e}")
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown"
        )
    
    await update.message.delete()

def get_multiplayer_handlers():
    return [
        CommandHandler("multiplayer", multiplayer),
        CommandHandler("extend", extend_time),
        CommandHandler("stop", stop_game),
        CommandHandler("list", list_players),
        CallbackQueryHandler(MButton_join, pattern='^Mjoin_[\s\S]*$'),
        CallbackQueryHandler(Mhandle_remove_button, pattern='^Mremove_[\s\S]*$'),
        CallbackQueryHandler(Mhandle_play_button, pattern='^Mplay_[\s\S]*$'),
        CallbackQueryHandler(Mhandle_cancel_button, pattern='^Mcancel_[\s\S]*$')
    ]
