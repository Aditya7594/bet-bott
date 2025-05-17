from __future__ import annotations

import logging
from pymongo import MongoClient
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import time as time_module
import asyncio
from functools import lru_cache, wraps
from collections import defaultdict
from typing import Dict, List, Optional

# Reduce logging level to WARNING
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger("Multiplayer")

# Command throttling settings
THROTTLE_RATE = 1.0  # seconds between commands
THROTTLE_BURST = 3   # number of commands allowed in burst

# Command throttling decorator
def throttle_command(rate=THROTTLE_RATE, burst=THROTTLE_BURST):
    def decorator(func):
        last_called = {}
        tokens = defaultdict(lambda: burst)
        last_update = {}

        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            current_time = time_module.time()

            # Initialize user's last called time
            if user_id not in last_called:
                last_called[user_id] = 0
                tokens[user_id] = burst

            # Check if enough time has passed to add a token
            time_passed = current_time - last_called[user_id]
            if time_passed >= rate:
                new_tokens = int(time_passed / rate)
                tokens[user_id] = min(burst, tokens[user_id] + new_tokens)
                last_called[user_id] = current_time

            # Check if user has tokens available
            if tokens[user_id] <= 0:
                await update.message.reply_text(
                    f"Please wait {rate:.1f} seconds before using this command again."
                )
                return

            # Use a token and execute the command
            tokens[user_id] -= 1
            return await func(update, context, *args, **kwargs)

        return wrapper
    return decorator

# Update filter function
def should_process_update(update: Update) -> bool:
    """Filter updates to reduce processing load."""
    if not update or not update.effective_user:
        return False
    
    # Skip updates from bots
    if update.effective_user.is_bot:
        return False
    
    # Skip non-message updates
    if not update.message and not update.callback_query:
        return False
    
    return True

# MongoDB setup with connection pooling
try:
    client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot',
                        serverSelectionTimeoutMS=5000,
                        maxPoolSize=50,
                        minPoolSize=10,
                        maxIdleTimeMS=30000)
    db = client['telegram_bot']
    user_collection = db['users']
    game_collection = db["multiplayer_games"]
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    user_collection = None
    game_collection = None

# Use defaultdict for better performance
multiplayer_games = defaultdict(dict)
games_lock = asyncio.Lock()
group_message_ids = defaultdict(int)
turn_timers = defaultdict(dict)
player_dm_message_ids = defaultdict(int)
turn_reminder_tasks = defaultdict(dict)

# Fix pytz import for environments where it may not be installed
try:
    import pytz
    UTC = pytz.UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

@lru_cache(maxsize=100)
def get_current_utc_time():
    """Get current time in UTC with timezone info."""
    return datetime.now(UTC)

def ensure_utc(dt):
    """Ensure datetime is timezone-aware and in UTC."""
    if dt is None:
        logger.debug("Received None datetime in ensure_utc")
        return None
    if dt.tzinfo is None:
        logger.warning(f"Naive datetime encountered: {dt}")
        # Handle pytz timezone localization correctly
        if 'pytz' in globals() and isinstance(UTC, pytz.UTC.__class__):
            dt = UTC.localize(dt)  # Use pytz's localize method
        else:
            dt = dt.replace(tzinfo=UTC)  # Fallback for non-pytz timezones
        logger.debug(f"Converted to UTC: {dt}")
        return dt
    if dt.tzinfo != UTC:
        logger.debug(f"Converting from {dt.tzinfo} to UTC: {dt}")
        dt = dt.astimezone(UTC)
    return dt

# Function to get user first name with caching
user_name_cache = {}

async def get_user_name_cached(user_id, context):
    if user_id in user_name_cache:
        return user_name_cache[user_id]
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name if chat.first_name else f"Player {user_id}"
        user_name_cache[user_id] = name
        return name
    except Exception as e:
        logger.error(f"Error getting user name for {user_id}: {e}")
        return f"Player {user_id}"

async def update_last_move(playing_id: str):
    """Update the last move time with proper timezone handling."""
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
        keyboard = [[InlineKeyboardButton("🎮 Start Bot", url=f"t.me/{bot_username}")]]
        user_tag = f"@{user.username}" if user.username else user.first_name if user.first_name else user_id

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ {user_tag}, please start the bot first!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return False
    return True

async def get_game_data(playing_id: str) -> dict:
    playing_id = str(playing_id)
    async with games_lock:
        if playing_id in multiplayer_games:
            return multiplayer_games[playing_id]
        game_data = game_collection.find_one({"playing_id": playing_id})
        if game_data:
            # Convert all relevant datetime fields
            for key in ["last_move", "start_time", "last_action"]:
                if key in game_data:
                    game_data[key] = ensure_utc(game_data[key])
            game = {k: v for k, v in game_data.items() if k != "_id"}
            multiplayer_games[playing_id] = game
            return game
        return None

@throttle_command()
async def multiplayer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle multiplayer command with throttling."""
    if not should_process_update(update):
        return

    user = update.effective_user
    user_id = str(user.id)
    
    # Get user data with caching
    user_data = get_user_by_id_cached(user_id)
    if not user_data:
        await update.message.reply_text("Please use /start first to register.")
        return

    # Check if user has enough credits
    if user_data.get('credits', 0) < 100:
        await update.message.reply_text("You need at least 100 credits to play.")
        return

    # Create game state
    game_id = str(random.randint(100000, 999999))
    multiplayer_games[game_id] = {
        'host': user_id,
        'players': [user_id],
        'bet_amount': 100,
        'status': 'waiting',
        'current_turn': user_id,
        'last_action': get_current_utc_time()
    }

    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("Join Game", callback_data=f"multiplayer_join_{game_id}")],
        [InlineKeyboardButton("Start Game", callback_data=f"multiplayer_start_{game_id}")]
    ]

    message = await update.message.reply_text(
        f"🎮 Multiplayer Game\n\n"
        f"Game ID: {game_id}\n"
        f"Host: {get_user_name_cached(user_id)}\n"
        f"Bet: {multiplayer_games[game_id]['bet_amount']} credits\n"
        f"Players: 1/4\n\n"
        f"Waiting for players to join...",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    group_message_ids[game_id] = message.message_id

async def handle_multiplayer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle multiplayer game callbacks with async optimization."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    action, game_id = query.data.split('_')[1:3]

    if game_id not in multiplayer_games:
        await query.edit_message_text("Game expired. Use /multiplayer to start a new game.")
        return

    game = multiplayer_games[game_id]

    if action == "join":
        if user_id in game['players']:
            await query.answer("You're already in this game!")
            return

        if len(game['players']) >= 4:
            await query.answer("Game is full!")
            return

        game['players'].append(user_id)
        
        # Update game message
        players_text = "\n".join([f"- {get_user_name_cached(pid)}" for pid in game['players']])
        keyboard = [
            [InlineKeyboardButton("Join Game", callback_data=f"multiplayer_join_{game_id}")],
            [InlineKeyboardButton("Start Game", callback_data=f"multiplayer_start_{game_id}")]
        ]

        await query.edit_message_text(
            f"🎮 Multiplayer Game\n\n"
            f"Game ID: {game_id}\n"
            f"Host: {get_user_name_cached(game['host'])}\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Players ({len(game['players'])}/4):\n{players_text}\n\n"
            f"Waiting for players to join...",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "start":
        if user_id != game['host']:
            await query.answer("Only the host can start the game!")
            return

        if len(game['players']) < 2:
            await query.answer("Need at least 2 players to start!")
            return

        game['status'] = 'playing'
        game['current_turn'] = game['players'][0]
        
        # Start game
        players_text = "\n".join([f"- {get_user_name_cached(pid)}" for pid in game['players']])
        keyboard = [
            [InlineKeyboardButton("Roll", callback_data=f"multiplayer_roll_{game_id}")]
        ]

        await query.edit_message_text(
            f"🎮 Multiplayer Game\n\n"
            f"Game ID: {game_id}\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Players:\n{players_text}\n\n"
            f"Current Turn: {get_user_name_cached(game['current_turn'])}\n"
            f"Roll the dice!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "roll":
        if user_id != game['current_turn']:
            await query.answer("It's not your turn!")
            return

        # Roll dice
        roll = random.randint(1, 6)
        next_player_index = (game['players'].index(user_id) + 1) % len(game['players'])
        game['current_turn'] = game['players'][next_player_index]

        # Update game message
        players_text = "\n".join([f"- {get_user_name_cached(pid)}" for pid in game['players']])
        keyboard = [
            [InlineKeyboardButton("Roll", callback_data=f"multiplayer_roll_{game_id}")]
        ]

        await query.edit_message_text(
            f"🎮 Multiplayer Game\n\n"
            f"Game ID: {game_id}\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Players:\n{players_text}\n\n"
            f"{get_user_name_cached(user_id)} rolled a {roll}!\n"
            f"Current Turn: {get_user_name_cached(game['current_turn'])}\n"
            f"Roll the dice!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def register_handlers(application: Application) -> None:
    """Register handlers with throttling."""
    # Add throttling handler
    application.add_handler(ThrottlingHandler(THROTTLE_RATE, THROTTLE_BURST))

    # Register command handlers with throttling
    application.add_handler(CommandHandler("multiplayer", throttle_command()(multiplayer)))
    
    # Register callback query handler
    application.add_handler(CallbackQueryHandler(handle_multiplayer_callback, pattern="^multiplayer_"))
    
    logger.info("Multiplayer game handlers registered successfully")

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
        start_time = ensure_utc(game["start_time"])
        time_left = (start_time - get_current_utc_time()).total_seconds()
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
        game["start_time"] = get_current_utc_time() + timedelta(seconds=15)
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one({"playing_id": playing_id}, {"$set": {"status": "ready", "start_time": game["start_time"]}})
        asyncio.create_task(start_game_countdown(playing_id, context))

async def start_game_countdown(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game:
        return
    while True:
        now = get_current_utc_time()
        start_time = ensure_utc(game["start_time"])
        if start_time is None:
            break
        time_left = (start_time - now).total_seconds()
        if time_left <= 0:
            await asyncio.create_task(start_game(playing_id, context))
            break
        elif 0 < time_left <= 6:
            if game.get("countdown_message") != "6":
                game_message = await context.bot.edit_message_text(
                    chat_id=game["group_chat_id"],
                    message_id=game["message_id"],
                    text="Game will start in 6 seconds...",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"Mjoin_batter_{playing_id}")],
                        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"Mjoin_bowler_{playing_id}")],
                        [InlineKeyboardButton("❌ Remove Me", callback_data=f"Mremove_{playing_id}")]
                    ]),
                    parse_mode="Markdown"
                )
                game["message_id"] = game_message.message_id
                game["countdown_message"] = "6"
                async with games_lock:
                    multiplayer_games[playing_id] = game
                game_collection.update_one({"playing_id": playing_id}, {"$set": {"message_id": game_message.message_id}})
        await asyncio.sleep(1)
        game = await get_game_data(playing_id)
        if not game:
            break

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
        {"$set": game}
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
        start_time = ensure_utc(game["start_time"])
        time_left = (start_time - get_current_utc_time()).total_seconds()
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
        game["start_time"] = get_current_utc_time() + timedelta(seconds=15)
        async with games_lock:
            multiplayer_games[playing_id] = game
        game_collection.update_one({"playing_id": playing_id}, {"$set": {"status": "ready", "start_time": game["start_time"]}})
        asyncio.create_task(start_game_countdown(playing_id, context))

async def start_game(playing_id: str, context: CallbackContext) -> None:
    """Start a new game with proper timezone handling."""
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when starting")
        return

    current_time = get_current_utc_time()
    logger.info(f"Starting game {playing_id} at {current_time}")
    
    game["status"] = "playing"
    game["start_time"] = current_time
    game["current_batter"] = game["batters"][0] if game["batters"] else None
    game["current_bowler"] = game["bowlers"][0] if game["bowlers"] else None
    game["team_a"] = game["batters"].copy()
    game["team_b"] = game["bowlers"].copy()
    game["last_move"] = current_time
    game["last_action"] = current_time  # Add this to ensure last_action is set
    
    # Save game state
    async with games_lock:
        multiplayer_games[playing_id] = game
    try:
        game_collection.update_one({"playing_id": playing_id}, {"$set": game})
        logger.info(f"Game state saved for {playing_id}")
    except Exception as e:
        logger.error(f"Error saving game state for {playing_id}: {e}")
        return

    # Notify players about their roles
    current_batter = game["current_batter"]
    current_bowler = game["current_bowler"]
    
    try:
        batter_name = await get_user_name_cached(current_batter, context)
        bowler_name = await get_user_name_cached(current_bowler, context)
        
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=f"🎮 *Game Started!*\n\n"
                 f"🎯 {batter_name} is batting\n"
                 f"🎳 {bowler_name} is bowling\n\n"
                 f"Use /current to see current players",
            parse_mode="Markdown"
        )
        logger.info(f"Game start notification sent for {playing_id}")
    except Exception as e:
        logger.error(f"Error sending game start notification for {playing_id}: {e}")
    
    # Start the game timeout checker
    asyncio.create_task(game_timeout_checker(playing_id, context))
    logger.debug(f"Timeout checker started for game {playing_id}")
    
    # Send initial buttons to current players
    await send_player_buttons(playing_id, context)

async def send_player_buttons(playing_id: str, context: CallbackContext) -> None:
    """Send appropriate buttons to current batter and bowler in DMs, delete old ones, and send clean group notification."""
    game = await get_game_data(playing_id)
    if not game:
        return

    current_batter = game.get("current_batter")
    current_bowler = game.get("current_bowler")
    
    if not current_batter or not current_bowler:
        logger.error(f"Missing current players in game {playing_id}")
        return

    # Create keyboard for players
    keyboard = [
        [
            InlineKeyboardButton(str(i), callback_data=f"Mplay_{playing_id}_{i}")
            for i in range(1, 4)
        ],
        [
            InlineKeyboardButton(str(i), callback_data=f"Mplay_{playing_id}_{i}")
            for i in range(4, 7)
        ]
    ]

    # Send buttons to current batter
    try:
        batter_msg = await context.bot.send_message(
            chat_id=current_batter,
            text="🎯 Your turn to bat! Choose a number (1-6):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        game["message_id"][current_batter] = batter_msg.message_id
    except Exception as e:
        logger.error(f"Error sending batter buttons: {e}")

    # Send buttons to current bowler
    try:
        bowler_msg = await context.bot.send_message(
            chat_id=current_bowler,
            text="🎯 Your turn to bowl! Choose a number (1-6):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        game["message_id"][current_bowler] = bowler_msg.message_id
    except Exception as e:
        logger.error(f"Error sending bowler buttons: {e}")

    # Update game state
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one(
        {"playing_id": playing_id},
        {"$set": {"message_id": game["message_id"]}}
    )

    # Send stylized notification in group (no buttons)
    batter_name = await get_user_name_cached(current_batter, context) if current_batter else 'None'
    bowler_name = await get_user_name_cached(current_bowler, context) if current_bowler else 'None'
    try:
        batter_chat = await context.bot.get_chat(current_batter) if current_batter else None
        bowler_chat = await context.bot.get_chat(current_bowler) if current_bowler else None
        batter_tag = f"@{batter_chat.username}" if batter_chat and batter_chat.username else batter_name
        bowler_tag = f"@{bowler_chat.username}" if bowler_chat and bowler_chat.username else bowler_name
    except Exception:
        batter_tag = batter_name
        bowler_tag = bowler_name

    group_text = (
        f"⏳ Over: {game['over']}.{game['ball']}\n"
        f"🔸 Batting: {batter_tag}\n"
        f"🔹 Bowling: {bowler_tag}\n"
        f"📊 Score: {game['score']}/{game['wickets']}"
    )
    if game['innings'] == 2 and game.get('target'):
        group_text += f" (Target: {game['target']})"
    group_text += f"\n\n<i>Check your DMs for your turn! 30 seconds to choose.</i>"

    try:
        msg = await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=group_text,
            parse_mode="HTML"
        )
        group_message_ids[playing_id] = msg.message_id
    except Exception as e:
        logger.error(f"Error sending group message: {e}")

async def game_timeout_checker(playing_id: str, context: CallbackContext):
    """Check for player timeouts and handle them."""
    while True:
        await asyncio.sleep(5)  # Check every 5 seconds
        game = await get_game_data(playing_id)
        if not game or game["status"] != "playing":
            break

        current_time = get_current_utc_time()
        last_move = ensure_utc(game.get("last_move"))
        
        if last_move:
            time_diff = (current_time - last_move).total_seconds()
            logger.debug(f"Time since last move: {time_diff} seconds")
            
            if time_diff > 30:
                logger.info(f"Timeout detected for game {playing_id} after {time_diff} seconds")
                # Handle timeout
                current_batter = game.get("current_batter")
                current_bowler = game.get("current_bowler")
                
                # Only move to next player if they haven't made their choice
                if game.get("batter_choice") is None or game.get("bowler_choice") is None:
                    logger.info(f"Moving to next players in game {playing_id}")
                    # Move to next player
                    if current_batter in game["batters"]:
                        next_batter_index = (game["batters"].index(current_batter) + 1) % len(game["batters"])
                        game["current_batter"] = game["batters"][next_batter_index]
                        logger.debug(f"New batter: {game['current_batter']}")
                    
                    if current_bowler in game["bowlers"]:
                        next_bowler_index = (game["bowlers"].index(current_bowler) + 1) % len(game["bowlers"])
                        game["current_bowler"] = game["bowlers"][next_bowler_index]
                        logger.debug(f"New bowler: {game['current_bowler']}")
                    
                    # Update game state
                    game["last_move"] = current_time
                    async with games_lock:
                        multiplayer_games[playing_id] = game
                    game_collection.update_one({"playing_id": playing_id}, {"$set": game})
                    
                    # Notify players
                    await context.bot.send_message(
                        chat_id=game["group_chat_id"],
                        text="⏰ *Timeout!* Moving to next players...",
                        parse_mode="Markdown"
                    )
                    
                    # Send new buttons
                    await send_player_buttons(playing_id, context)

async def process_ball_result(playing_id: str, context: CallbackContext) -> None:
    game = await get_game_data(playing_id)
    if not game or game["status"] != "playing":
        return

    batter_choice = game.get("batter_choice")
    bowler_choice = game.get("bowler_choice")

    if batter_choice is None or bowler_choice is None:
        return

    wicket_fell = False
    # Check if numbers match (wicket)
    if batter_choice == bowler_choice:
        game["wickets"] += 1
        wicket_fell = True
        result_text = f"🎯 OUT! Batter chose {batter_choice} and bowler chose {bowler_choice}!"
        
        # Update bowler stats - track wickets for all bowlers
        bowler_id = game["current_bowler"]
        if str(bowler_id) not in game["bowler_stats"]:
            game["bowler_stats"][str(bowler_id)] = {"wickets": 0, "runs": 0}
        game["bowler_stats"][str(bowler_id)]["wickets"] += 1
        
        # Add to match details
        game["match_details"].append((game["over"], game["ball"], 0, True))
        
        # Move to next batter if not all out
        if game["wickets"] < game["max_wickets"]:
            if game["current_batter"] in game["batters"]:
                # Remove the out batter from active list
                game["batters"].remove(game["current_batter"])
                if game["batters"]:  # If there are still batters left
                    game["current_batter"] = game["batters"][0]
                else:
                    # All batters are out
                    if game["innings"] == 2 and game["score"] >= game["target"]:
                        await declare_winner(playing_id, context)
                        return
                    await end_innings(playing_id, context)
                    return
        else:
            # All out - end innings
            if game["innings"] == 2 and game["score"] >= game["target"]:
                await declare_winner(playing_id, context)
                return
            await end_innings(playing_id, context)
            return
    else:
        runs = batter_choice
        game["score"] += runs
        result_text = f"💥 {runs} run{'s' if runs > 1 else ''} scored! Batter chose {batter_choice} and bowler chose {bowler_choice}"
        
        # Update batter stats
        batter_id = game["current_batter"]
        if str(batter_id) not in game["batter_stats"]:
            game["batter_stats"][str(batter_id)] = {"runs": 0}
        game["batter_stats"][str(batter_id)]["runs"] += runs
        
        # Update bowler stats - track runs conceded
        bowler_id = game["current_bowler"]
        if str(bowler_id) not in game["bowler_stats"]:
            game["bowler_stats"][str(bowler_id)] = {"wickets": 0, "runs": 0}
        game["bowler_stats"][str(bowler_id)]["runs"] += runs
        
        # Add to match details
        game["match_details"].append((game["over"], game["ball"], runs, False))

    game["batter_choice"] = None
    game["bowler_choice"] = None
    game["last_move"] = get_current_utc_time()

    # Update ball and over
    game["ball"] += 1
    if game["ball"] >= 6:
        game["ball"] = 0
        game["over"] += 1
        
        # Rotate bowler after each over
        if game["bowlers"]:
            current_bowler_index = game["bowlers"].index(game["current_bowler"])
            next_bowler_index = (current_bowler_index + 1) % len(game["bowlers"])
            game["current_bowler"] = game["bowlers"][next_bowler_index]
            
            # Notify group about bowler change
            new_bowler_name = await get_user_name_cached(game["current_bowler"], context)
            try:
                new_bowler_chat = await context.bot.get_chat(game["current_bowler"])
                new_bowler_tag = f"@{new_bowler_chat.username}" if new_bowler_chat.username else new_bowler_name
            except Exception:
                new_bowler_tag = new_bowler_name
                
            await context.bot.send_message(
                chat_id=game["group_chat_id"],
                text=f"🔄 New over! {new_bowler_tag} is now bowling.",
                parse_mode="HTML"
            )

    # Save game state
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one({"playing_id": playing_id}, {"$set": game})

    # Check for game end conditions
    if game["innings"] == 2:
        if game["score"] >= game["target"]:
            # Target met or exceeded - end game immediately
            await declare_winner(playing_id, context)
            return
        elif game["over"] >= game["max_overs"]:
            # Overs completed - end innings
            await end_innings(playing_id, context)
            return
    elif game["over"] >= game["max_overs"]:
        # First innings overs completed
        await end_innings(playing_id, context)
        return

    # Send result to group and update interface
    await update_multiplayer_group_message(playing_id, context, result_text)

async def innings_check(game_id: str, game_data: dict = None) -> None:
    """Check if innings should end and handle the transition."""
    game = game_data or await get_game_data(game_id)
    if not game or game["status"] != "playing":
        return

    # Check if innings should end
    if game["innings"] == 1:
        if game["over"] >= game["max_overs"] or game["wickets"] >= game["max_wickets"]:
            await end_innings(game_id, None)  # context is not needed for end_innings
    else:  # innings == 2
        if (game["over"] >= game["max_overs"] or 
            game["wickets"] >= game["max_wickets"] or 
            game["score"] >= game["target"]):
            await declare_winner(game_id, None)  # context is not needed for declare_winner

async def end_innings(playing_id: str, context: CallbackContext = None) -> None:
    """Handle the end of an innings and transition to the next."""
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when ending innings")
        return
    
    if game["innings"] == 1:
        # First innings completed
        first_innings_score = game["score"]
        game["target"] = first_innings_score + 1  # Target is first innings score + 1
        game["innings"] = 2
        game["score"] = 0
        game["over"] = 0
        game["ball"] = 0
        game["wickets"] = 0
        current_time = get_current_utc_time()
        game["last_action"] = current_time
        game["last_move"] = current_time
        
        # Store original teams
        game["team_a"] = game["batters"].copy()
        game["team_b"] = game["bowlers"].copy()
        
        # Swap teams for second innings
        game["batters"] = game["team_b"].copy()
        game["bowlers"] = game["team_a"].copy()
        
        # Set current players
        game["current_batter"] = game["batters"][0] if game["batters"] else None
        game["current_bowler"] = game["bowlers"][0] if game["bowlers"] else None
        
        # Reset choices for new innings
        game["batter_choice"] = None
        game["bowler_choice"] = None
        
        # Save game state
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
                "last_action": game["last_action"],
                "last_move": game["last_move"],
                "batter_choice": None,
                "bowler_choice": None
            }}
        )
        
        if context:  # Only send messages if context is provided
            # Get team names for the message
            team_a_players = game.get("team_a", [])
            team_b_players = game.get("team_b", [])
            team_a_text = "\n".join([f"- {await get_user_name_cached(uid, context)}" for uid in team_a_players]) if team_a_players else "None"
            team_b_text = "\n".join([f"- {await get_user_name_cached(uid, context)}" for uid in team_b_players]) if team_b_players else "None"
            
            innings_message = (
                f"🏏 *First Innings Completed!*\n\n"
                f"Team A Score: {first_innings_score}/{game['wickets']}\n"
                f"Team B Target: {game['target']} runs\n\n"
                f"Team A (First Innings):\n{team_a_text}\n\n"
                f"Team B (Second Innings):\n{team_b_text}\n\n"
                f"Roles have been swapped. Game will continue shortly."
            )
            
            # Send innings message to group
            await context.bot.send_message(
                chat_id=game["group_chat_id"],
                text=innings_message,
                parse_mode="Markdown"
            )
            
            # Wait a few seconds before starting second innings
            await asyncio.sleep(3)
            
            # Start second innings by sending buttons to players
            await send_player_buttons(playing_id, context)
    else:
        # Second innings completed - check if target was met
        if game["score"] >= game.get("target", 0):
            await declare_winner(playing_id, context)
        else:
            await declare_winner(playing_id, context)

async def declare_winner(playing_id: str, context: CallbackContext = None) -> None:
    """Declare the winner and end the game."""
    game = await get_game_data(playing_id)
    if not game:
        logger.error(f"Game {playing_id} not found when declaring winner")
        return
    
    # Save final game state
    game_collection.update_one(
        {"playing_id": playing_id},
        {"$set": game}
    )
    
    # Clean up game state
    async with games_lock:
        if playing_id in multiplayer_games:
            del multiplayer_games[playing_id]
    
    # Remove from database
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
                message_id=game.get("player_messages", {}).get(str(uid), uid),
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
    
    current_time = get_current_utc_time()
    game["start_time"] = current_time + timedelta(seconds=15)
    async with games_lock:
        multiplayer_games[playing_id] = game
    game_collection.update_one({"playing_id": playing_id}, {"$set": {"start_time": game["start_time"]}})
    
    start_time = ensure_utc(game["start_time"])
    time_left = int((start_time - current_time).total_seconds())
    await context.bot.edit_message_text(
        chat_id=game["group_chat_id"],
        message_id=game["message_id"],
        text=f"Time extended! Game will start in {time_left} seconds...",
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
        if game.get("message_id"):
            try:
                await context.bot.edit_message_text(
                    chat_id=game["group_chat_id"],
                    message_id=game["message_id"],
                    text="🛑 Game stopped by admin!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error editing stop message: {e}")
                # Send new message if edit fails
                await context.bot.send_message(
                    chat_id=game["group_chat_id"],
                    text="🛑 Game stopped by admin!",
                    parse_mode="Markdown"
                )
        
        # Clean up player messages
        for uid in game["batters"] + game["bowlers"]:
            try:
                prev_dm_id = player_dm_message_ids.get((uid, 'bat')) or player_dm_message_ids.get((uid, 'bowl'))
                if prev_dm_id:
                    await context.bot.delete_message(chat_id=uid, message_id=prev_dm_id)
            except Exception as e:
                logger.error(f"Error cleaning up player message for {uid}: {e}")
        
        # Clean up game state
        if playing_id in multiplayer_games:
            async with games_lock:
                del multiplayer_games[playing_id]
        
        # Remove from database
        game_collection.delete_one({"playing_id": playing_id})
        
        # Try to delete the command message
        try:
            await update.message.delete()
        except Exception as e:
            logger.error(f"Error deleting command message: {e}")
            
    except Exception as e:
        logger.error(f"Error in stop_game: {e}")
        await update.message.reply_text("⚠️ Error stopping game. Please try again.")

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

async def show_current_players(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playing_id = str(chat_id)
    game = await get_game_data(playing_id)
    if not game:
        await update.message.reply_text("No active game in this chat!")
        return
    if game["status"] == "waiting":
        await update.message.reply_text("Game hasn't started yet!")
        return
    current_batter = game.get("current_batter")
    current_bowler = game.get("current_bowler")
    over = game.get("over", 0)
    ball = game.get("ball", 0)
    score = game.get("score", 0)
    wickets = game.get("wickets", 0)
    batter_name = await get_user_name_cached(current_batter, context) if current_batter else 'None'
    bowler_name = await get_user_name_cached(current_bowler, context) if current_bowler else 'None'
    batter_tag = f"@{(await context.bot.get_chat(current_batter)).username}" if current_batter and (await context.bot.get_chat(current_batter)).username else batter_name
    bowler_tag = f"@{(await context.bot.get_chat(current_bowler)).username}" if current_bowler and (await context.bot.get_chat(current_bowler)).username else bowler_name
    text = f"⏳ Over: {over}.{ball}\n"
    text += f"🔸 Batting: {batter_tag}\n"
    text += f"🔹 Bowling: {bowler_tag}\n"
    text += f"📊 Score: {score}/{wickets}"
    await update.message.reply_text(text, parse_mode="Markdown")

async def Mhandle_play_button(update: Update, context: CallbackContext) -> None:
    """Handle player choices (batter or bowler)."""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        parts = query.data.split('_')
        if len(parts) != 3:
            logger.error(f"Invalid callback data format: {query.data}")
            await query.answer("Invalid game data")
            return
            
        choice = parts[1]
        playing_id = parts[2]
        
        game = await get_game_data(playing_id)
        if not game:
            logger.error(f"Game not found for ID: {playing_id}")
            await query.answer("Game not found or expired!")
            return
        
        if game["status"] != "playing":
            logger.warning(f"Game {playing_id} is not active. Status: {game['status']}")
            await query.answer("Game is not active!")
            return
        
        if user_id != game.get("current_batter") and user_id != game.get("current_bowler"):
            logger.warning(f"User {user_id} tried to play out of turn")
            await query.answer("It's not your turn!")
            return
        
        # Convert choice to integer
        try:
            number = int(choice)
            if number < 1 or number > 6:
                logger.warning(f"Invalid choice {number} from user {user_id}")
                await query.answer("Invalid choice! Choose 1-6")
                return
        except ValueError:
            logger.error(f"Invalid choice format: {choice}")
            await query.answer("Invalid choice! Choose 1-6")
            return
        
        # Update game state
        if user_id == game.get("current_batter"):
            if game.get("batter_choice") is not None:
                logger.warning(f"Batter {user_id} tried to play twice")
                await query.answer("You've already made your choice!")
                return
            game["batter_choice"] = number
        else:  # bowler
            if game.get("bowler_choice") is not None:
                logger.warning(f"Bowler {user_id} tried to play twice")
                await query.answer("You've already made your choice!")
                return
            game["bowler_choice"] = number
        
        # Save game state
        async with games_lock:
            multiplayer_games[playing_id] = game
        try:
            game_collection.update_one({"playing_id": playing_id}, {"$set": game})
        except Exception as e:
            logger.error(f"Database error updating game {playing_id}: {e}")
            await query.answer("Error saving game state!")
            return
        
        await query.answer(f"Your choice: {number}")
        
        # If both players have made their choices, process the result
        if game.get("batter_choice") is not None and game.get("bowler_choice") is not None:
            await process_ball_result(playing_id, context)
            
    except Exception as e:
        logger.error(f"Unexpected error in Mhandle_play_button: {e}", exc_info=True)
        await query.answer("An error occurred!")

async def update_multiplayer_group_message(playing_id: str, context: CallbackContext, result_text: str = None):
    game = await get_game_data(playing_id)
    if not game:
        return
    score = game['score']
    wickets = game['wickets']
    over = game['over']
    ball = game['ball']
    innings = game['innings']
    target = game.get('target')
    batter_id = game.get('current_batter')
    bowler_id = game.get('current_bowler')
    batter_name = await get_user_name_cached(batter_id, context) if batter_id else 'None'
    bowler_name = await get_user_name_cached(bowler_id, context) if bowler_id else 'None'
    
    # Format group message (no buttons in group)
    text = (
        f"⏳ Over: {over}.{ball}\n"
        f"🔸 Batting: {batter_name}\n"
        f"🔹 Bowling: {bowler_name}\n"
        f"📊 Score: {score}/{wickets}"
    )
    if innings == 2 and target:
        text += f" (Target: {target})"
    if result_text:
        text += f"\n\n{result_text}"

    # Update group message (no buttons)
    prev_msg_id = group_message_ids[playing_id]
    if prev_msg_id and prev_msg_id != game["message_id"]:
        try:
            await context.bot.delete_message(chat_id=game["group_chat_id"], message_id=prev_msg_id)
        except Exception as e:
            logger.error(f"Error deleting previous group message: {e}")
    
    try:
        msg = await context.bot.edit_message_text(
            chat_id=game["group_chat_id"],
            message_id=game["message_id"],
            text=text,
            parse_mode="HTML"
        )
        group_message_ids[playing_id] = msg.message_id
    except Exception as e:
        logger.error(f"Error updating group message: {e}")
    
    # Send buttons to players in DMs
    await send_player_buttons(playing_id, context)
    
    # Start the 30-second timer
    asyncio.create_task(start_turn_timer(playing_id, context))

async def start_turn_timer(playing_id: str, context: CallbackContext):
    """Start a 30-second timer for the current turn."""
    try:
        # Wait for exactly 30 seconds
        await asyncio.sleep(30)
        
        game = await get_game_data(playing_id)
        if not game or game["status"] != "playing":
            return

        # Only switch players if they haven't made their choice
        if game.get("batter_choice") is None or game.get("bowler_choice") is None:
            batter_id = game.get("current_batter")
            bowler_id = game.get("current_bowler")
            
            # Get player names for notification
            try:
                batter_name = await get_user_name_cached(batter_id, context) if batter_id else 'None'
                bowler_name = await get_user_name_cached(bowler_id, context) if bowler_id else 'None'
                batter_chat = await context.bot.get_chat(batter_id) if batter_id else None
                bowler_chat = await context.bot.get_chat(bowler_id) if bowler_id else None
                batter_tag = f"@{batter_chat.username}" if batter_chat and batter_chat.username else batter_name
                bowler_tag = f"@{bowler_chat.username}" if bowler_chat and bowler_chat.username else bowler_name
            except Exception as e:
                logger.error(f"Error getting player names: {e}")
                batter_tag = "Batter"
                bowler_tag = "Bowler"

            # Clean up previous timeout message
            prev_msg_id = group_message_ids[playing_id]
            if prev_msg_id:
                try:
                    await context.bot.delete_message(chat_id=game["group_chat_id"], message_id=prev_msg_id)
                except Exception as e:
                    logger.error(f"Error deleting previous timeout message: {e}")

            # Notify group about timeout
            try:
                msg = await context.bot.send_message(
                    chat_id=game["group_chat_id"],
                    text=f"⏰ 30 seconds passed! {batter_tag} or {bowler_tag} did not play. Moving to next players.",
                    parse_mode="HTML"
                )
                group_message_ids[playing_id] = msg.message_id
            except Exception as e:
                logger.error(f"Error sending timeout message: {e}")

            # Move to next batter and bowler
            if batter_id in game["batters"]:
                next_batter_index = (game["batters"].index(batter_id) + 1) % len(game["batters"])
                game["current_batter"] = game["batters"][next_batter_index]
            if bowler_id in game["bowlers"]:
                next_bowler_index = (game["bowlers"].index(bowler_id) + 1) % len(game["bowlers"])
                game["current_bowler"] = game["bowlers"][next_bowler_index]

            # Reset choices and update timestamps
            current_time = get_current_utc_time()
            game["batter_choice"] = None
            game["bowler_choice"] = None
            game["last_move"] = current_time
            game["last_action"] = current_time

            # Save game state
            async with games_lock:
                multiplayer_games[playing_id] = game
            game_collection.update_one({"playing_id": playing_id}, {"$set": game})

            # Update group message and send new buttons
            await send_player_buttons(playing_id, context)
    except Exception as e:
        logger.error(f"Error in turn timer: {e}")

def get_multiplayer_handlers():
    return [
        CommandHandler("multiplayer", multiplayer),
        CommandHandler("current", show_current_players),
        CommandHandler("extend", extend_time),
        CommandHandler("stop", stop_game),
        CommandHandler("list", list_players),
        CallbackQueryHandler(MButton_join, pattern=r'^Mjoin_.*$'),
        CallbackQueryHandler(Mhandle_remove_button, pattern=r'^Mremove_.*$'),
        CallbackQueryHandler(Mhandle_play_button, pattern=r'^Mplay_.*$'),
        CallbackQueryHandler(Mhandle_cancel_button, pattern=r'^Mcancel_.*$')
    ]
