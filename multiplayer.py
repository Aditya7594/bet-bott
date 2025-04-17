from pymongo import MongoClient
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup,CallbackQuery
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from datetime import datetime, timedelta
import time
import pytz
import asyncio
from cricket import get_user_name_cached
from shared_state import shared

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

# Ensure UTC timezone is used consistently
def get_current_utc_time():
    return datetime.now(pytz.utc)

# Shared game state reference
multiplayer_games = shared.multiplayer_games

# Update last_move on every interaction
async def update_last_move(game_id: str):
    current_time = get_current_utc_time()
    try:
        game_collection.update_one(
            {"game_id": game_id},
            {"$set": {"last_move": current_time}}
        )
        if game_id in multiplayer_games:
            multiplayer_games[game_id]["last_move"] = current_time
        logger.info(f"Updated last_move for game {game_id} to {current_time}")
    except Exception as e:
        logger.error(f"Error updating last_move for game {game_id}: {e}")

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
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return False
    return True

async def get_game_data(game_id: str) -> dict:
    game_id = str(game_id)
    if game_id in shared.multiplayer_games:
        return shared.multiplayer_games[game_id]
    # Try to load from DB
    game_data = game_collection.find_one({"game_id": game_id})
    if game_data:
        game = {k: v for k, v in game_data.items() if k != "_id"}
        shared.multiplayer_games[game_id] = game
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

    game_id = str(chat_id)
    game_data = {
        "game_id": game_id,
        "batters": [],
        "bowlers": [],
        "max_overs": max_overs,
        "max_wickets": max_wickets,
        "group_chat_id": chat_id,
        "status": "waiting",
        "message_id": None,
        "last_move": get_current_utc_time()
    }

    logger.info(f"[multiplayer] Creating new game with ID: {game_id}")
    multiplayer_games[game_id] = game_data
    logger.info(f"[multiplayer] Stored in multiplayer_games: {list(multiplayer_games.keys())}")

    game_collection.update_one({"game_id": game_id}, {"$set": game_data}, upsert=True)

    desc = f"🏏 *Cricket Match Started!*\n\nFormat: {max_overs} over{'s' if max_overs > 1 else ''}, {max_wickets} wicket{'s' if max_wickets > 1 else ''}\n\n"
    desc += "• Join as Batter or Bowler\n• Match will start once teams are full."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"join_batter_{game_id}")],
        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"join_bowler_{game_id}")],
        [InlineKeyboardButton("❌ Remove Me", callback_data=f"remove_{game_id}")]
    ])

    sent_message = await context.bot.send_message(chat_id=chat_id, text=desc, reply_markup=keyboard, parse_mode="Markdown")

    game_data["message_id"] = sent_message.message_id
    multiplayer_games[game_id]["message_id"] = sent_message.message_id
    game_collection.update_one({"game_id": game_id}, {"$set": {"message_id": sent_message.message_id}})

    logger.info(f"[multiplayer] Game created and message_id stored: {sent_message.message_id}")


async def handle_join_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    try:
        _, role, game_id = query.data.split('_', 2)
    except ValueError:
        await query.answer("Invalid callback!")
        return

    if not await check_user_started_bot(update, context):
        await query.answer("Start the bot first!")
        return

    game = await get_game_data(game_id)
    if not game:
        await query.answer("Game not found or expired!")
        return

    if game["status"] != "waiting":
        await query.answer("Game already started!")
        return

    user_id = int(user_id)
    
    if user_id in game["batters"] or user_id in game["bowlers"]:
        await query.answer("You're already in the game!")
        return

    if role == "batter":
        game["batters"].append(user_id)
    else:
        game["bowlers"].append(user_id)

    shared.multiplayer_games[game_id] = game
    game_collection.update_one({"game_id": game_id}, {"$set": {"batters": game["batters"], "bowlers": game["bowlers"]}})

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

    text = f"🏏 *Cricket Match Lobby*\n\nFormat: {game['max_overs']} overs, {game['max_wickets']} wickets\n\n"
    text += f"🔼 Batters ({len(batter_names)}/{game['max_wickets']}): {', '.join(batter_names) if batter_names else 'None'}\n"
    text += f"🔽 Bowlers ({len(bowler_names)}/{game['max_wickets']}): {', '.join(bowler_names) if bowler_names else 'None'}\n\n"
    text += f"Match starts when both sides are full."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"join_batter_{game_id}")],
        [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"join_bowler_{game_id}")],
        [InlineKeyboardButton("❌ Remove Me", callback_data=f"remove_{game_id}")]
    ])

    try:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")
        await query.answer("You joined as " + role.capitalize())
    except Exception as e:
        logger.error(f"Edit error: {e}")

    if len(game["batters"]) >= game["max_wickets"] and len(game["bowlers"]) >= game["max_wickets"]:
        await context.bot.send_message(chat_id=game["group_chat_id"], text="✅ Teams are ready! Game will begin soon.")
        game["status"] = "ready"
        shared.multiplayer_games[game_id] = game
        game_collection.update_one({"game_id": game_id}, {"$set": {"status": "ready"}})
        asyncio.create_task(delayed_game_start(game_id, context))

async def delayed_game_start(game_id: str, context: CallbackContext, delay_seconds: int = 2) -> None:
    await asyncio.sleep(delay_seconds)
    await start_game(game_id, context)

async def handle_remove_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id = query.data.split('_', 1)
    
    if not await check_user_started_bot(update, context):
        await query.answer("You need to start the bot first!")
        return
    
    game = await get_game_data(game_id)
    if not game:
        await query.answer("Game not found or expired!")
        await query.edit_message_text(
            text="This game has expired or been deleted. Start a new game with /multiplayer command.",
            reply_markup=None
        )
        return
    
    if game["status"] != "waiting":
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
    
    shared.multiplayer_games[game_id] = game
    game_collection.update_one(
        {"game_id": game_id},
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
    
    game_desc = f"🏏 *Cricket Tournament*\n\n"
    game_desc += f"Format: {game['max_overs']} over{'s' if game['max_overs'] > 1 else ''}, {game['max_wickets']} wicket{'s' if game['max_wickets'] > 1 else ''}\n\n"
    game_desc += f"🔼 Batters ({len(game['batters'])}/{game['max_wickets']}): {', '.join(batter_names) if batter_names else 'None'}\n"
    game_desc += f"🔽 Bowlers ({len(game['bowlers'])}/{game['max_wickets']}): {', '.join(bowler_names) if bowler_names else 'None'}\n\n"
    game_desc += f"• Teams will start once {game['max_wickets']} players join each role"
    
    await query.edit_message_text(
        text=game_desc,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔼 Join as Batter", callback_data=f"join_batter_{game_id}")],
            [InlineKeyboardButton("🔽 Join as Bowler", callback_data=f"join_bowler_{game_id}")],
            [InlineKeyboardButton("❌ Remove Me", callback_data=f"remove_{game_id}")]
        ]),
        parse_mode="Markdown"
    )
    
    await query.answer("Removed successfully!")

async def start_game(game_id: str, context: CallbackContext) -> None:
    game = await get_game_data(game_id)
    query = Update.callback_query
    if not game:
        await query.answer("Game not found or expired!")
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
    
    for user_id in game["batters"] + game["bowlers"]:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🎮 Game has started! You are part of the tournament.\n\n"
                    "Wait for your turn to bat or bowl."
            )
        except Exception as e:
            logger.error(f"Error notifying player {user_id}: {e}")
    
    game["status"] = "started"
    game["current_batter"] = game["batters"][0]
    game["current_bowler"] = game["bowlers"][0]
    game["batter_choice"] = None
    game["bowler_choice"] = None
    game["score"] = 0
    game["wickets"] = 0
    game["over"] = 0
    game["ball"] = 0
    game["innings"] = 1
    
    shared.multiplayer_games[game_id] = game
    game_collection.update_one(
        {"game_id": game_id},
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
            "innings": game["innings"]
        }}
    )
    
    await update_game_interface(game_id, context)

async def update_game_interface(game_id: str, context: CallbackContext) -> None:
    game = await get_game_data(game_id)
    if not game:
        logger.error(f"Game {game_id} not found when updating interface")
        return
    
    game["batter_choice"] = None
    game["bowler_choice"] = None
    
    shared.multiplayer_games[game_id] = game
    game_collection.update_one(
        {"game_id": game_id},
        {"$set": {
            "batter_choice": None,
            "bowler_choice": None
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
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_id}|{i}"))
        if len(row) == 3:
            batter_keyboard.append(row)
            row = []
    
    bowler_keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_id}|{i}"))
        if len(row) == 3:
            bowler_keyboard.append(row)
            row = []
    
    for user_id in game["batters"] + game["bowlers"]:
        try:
            if user_id == batter_id:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=status_text + f"🔸 Your turn to bat! Choose a number (1-6):",
                    reply_markup=InlineKeyboardMarkup(batter_keyboard),
                    parse_mode="Markdown"
                )
            elif user_id == bowler_id:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=status_text + f"🔹 Your turn to bowl! Choose a number (1-6):",
                    reply_markup=InlineKeyboardMarkup(bowler_keyboard),
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=status_text + f"⌛ Waiting for batter and bowler to play...",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error sending interface to {user_id}: {e}")

async def handle_play_button(update: Update, context: CallbackContext) -> None:
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
            
        game_id = game_parts[0]
        number = int(game_parts[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing play data: {e}, data: {query.data}")
        await query.answer("Invalid game data")
        return
    
    user_id = int(user_id)
    
    game = await get_game_data(game_id)
    if not game:
        await query.answer("Game not found or expired!")
        return
    
    if game["status"] != "started":
        await query.answer("This game is not active!")
        return
    
    if user_id != game["current_batter"] and user_id != game["current_bowler"]:
        await query.answer("It's not your turn!")
        return
    
    await update_last_move(game_id)

    if user_id == game["current_batter"]:
        if game.get("batter_choice") is not None:
            await query.answer("You've already made your choice!")
            return
            
        game["batter_choice"] = number
        
        shared.multiplayer_games[game_id] = game
        game_collection.update_one(
            {"game_id": game_id},
            {"$set": {"batter_choice": number}}
        )
        
        await query.answer(f"Your choice: {number}")
        
        if game.get("bowler_choice") is not None:
            await process_ball_result(game_id, context, query)
    
    elif user_id == game["current_bowler"]:
        if game.get("bowler_choice") is not None:
            await query.answer("You've already made your choice!")
            return
            
        game["bowler_choice"] = number
        
        shared.multiplayer_games[game_id] = game
        game_collection.update_one(
            {"game_id": game_id},
            {"$set": {"bowler_choice": number}}
        )
        
        await query.answer(f"Your choice: {number}")
        
        if game.get("batter_choice") is not None:
            await process_ball_result(game_id, context)

async def process_ball_result(game_id: str, context: CallbackContext, query: CallbackQuery) -> None:
    game = await get_game_data(game_id)
    if not game:
        logger.error(f"Game {game_id} not found when processing ball result")
        return
    
    batter_choice = game.get("batter_choice")
    bowler_choice = game.get("bowler_choice")

    if batter_choice is None or bowler_choice is None:
        logger.error(f"Missing choices for game {game_id}: batter={batter_choice}, bowler={bowler_choice}")
        return
    
    result_text = (
        f"🏏 *Ball Result*\n\n"
        f"Batter chose: {batter_choice}\n"
        f"Bowler chose: {bowler_choice}\n\n"
    )
    
    if batter_choice == bowler_choice:
        result_text += f"🎯 OUT! Batter is dismissed!"
        game["wickets"] += 1
        
        for user_id in game["batters"] + game["bowlers"]:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=result_text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error sending result to {user_id}: {e}")
        
        game["ball"] += 1
        if game["ball"] == 6:
            game["over"] += 1
            game["ball"] = 0
        
        if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
            shared.multiplayer_games[game_id] = game
            game_collection.update_one(
                {"game_id": game_id},
                {"$set": {
                    "wickets": game["wickets"],
                    "over": game["over"],
                    "ball": game["ball"]
                }}
            )
            await end_innings(game_id, context)
            return
        
        current_batter = game["current_batter"]
        game["batters"].remove(current_batter)
        game["batters"].append(current_batter)
        game["current_batter"] = game["batters"][0]
        
        shared.multiplayer_games[game_id] = game
        game_collection.update_one(
            {"game_id": game_id},
            {"$set": {
                "wickets": game["wickets"],
                "over": game["over"],
                "ball": game["ball"],
                "current_batter": game["current_batter"],
                "batters": game["batters"]
            }}
        )
    else:
        runs = batter_choice
        result_text += f"💥 {runs} run{'s' if runs > 1 else ''} scored!"
        game["score"] += runs
        
        if game["innings"] == 2 and game.get("target") and game["score"] >= game["target"]:
            for user_id in game["batters"] + game["bowlers"]:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=result_text,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error sending result to {user_id}: {e}")
                    
            shared.multiplayer_games[game_id] = game
            game_collection.update_one(
                {"game_id": game_id},
                {"$set": {"score": game["score"]}}
            )
            
            await end_innings(game_id, context)
            return
        
        game["ball"] += 1
        if game["ball"] == 6:
            game["over"] += 1
            game["ball"] = 0
            
            current_bowler = game["current_bowler"]
            game["bowlers"].remove(current_bowler)
            game["bowlers"].append(current_bowler)
            game["current_bowler"] = game["bowlers"][0]
        
        if game["over"] >= game["max_overs"]:
            shared.multiplayer_games[game_id] = game
            game_collection.update_one(
                {"game_id": game_id},
                {"$set": {
                    "score": game["score"],
                    "over": game["over"],
                    "ball": game["ball"],
                    "current_bowler": game["current_bowler"],
                    "bowlers": game["bowlers"]
                }}
            )
            
            await end_innings(game_id, context)
            return
        
        shared.multiplayer_games[game_id] = game
        game_collection.update_one(
            {"game_id": game_id},
            {"$set": {
                "score": game["score"],
                "over": game["over"],
                "ball": game["ball"],
                "current_bowler": game["current_bowler"],
                "bowlers": game["bowlers"]
            }}
        )
    
    await update_game_interface(game_id, context)

async def end_innings(game_id: str, context: CallbackContext) -> None:
    game = await get_game_data(game_id)
    if not game:
        logger.error(f"Game {game_id} not found when ending innings")
        return
    
    if game["innings"] == 1:
        game["target"] = game["score"] + 1
        game["innings"] = 2
        game["over"] = 0
        game["ball"] = 0
        game["wickets"] = 0
        game["batters"], game["bowlers"] = game["bowlers"], game["batters"]
        game["current_batter"] = game["batters"][0]
        game["current_bowler"] = game["bowlers"][0]
        
        shared.multiplayer_games[game_id] = game
        game_collection.update_one(
            {"game_id": game_id},
            {"$set": {
                "innings": game["innings"],
                "target": game["target"],
                "over": game["over"],
                "ball": game["ball"],
                "wickets": game["wickets"],
                "batters": game["batters"],
                "bowlers": game["bowlers"],
                "current_batter": game["current_batter"],
                "current_bowler": game["current_bowler"]
            }}
        )
        
        for user_id in game["batters"] + game["bowlers"]:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🏏 *Innings Completed!*\n\n"
                        f"First Innings Score: {game['score']}/{game['wickets']}\n"
                        f"Second Innings Target: {game['target']} runs\n\n"
                        f"Roles have been swapped. Game will continue shortly.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error notifying player {user_id}: {e}")
        
        await update_game_interface(game_id, context)
    else:
        await declare_winner(game_id, context)

async def declare_winner(game_id: str, context: CallbackContext, innings_result=None) -> None:
    game = await get_game_data(game_id)
    if not game:
        logger.error(f"Game {game_id} not found when declaring winner")
        return
    
    target = game.get("target", 0)
    first_innings_score = target - 1 if target else 0
    second_innings_score = game["score"]
    
    if game["innings"] == 2:
        if second_innings_score >= target:
            winner_team = "Second batting team"
            margin = f"by {game['max_wickets'] - game['wickets']} wickets"
        else:
            winner_team = "First batting team"
            margin = f"by {target - second_innings_score - 1} runs"
    else:
        winner_team = "Game incomplete"
        margin = ""
    
    result_message = innings_result if innings_result else ""
    result_message += (
        f"🏆 *GAME OVER!*\n\n"
        f"First Innings: {first_innings_score} runs\n"
        f"Second Innings: {second_innings_score}/{game['wickets']}\n\n"
        f"🏆 {winner_team} won {margin}!\n"
    )
    
    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
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

    for user_id in game["batters"] + game["bowlers"]:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=result_message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending result to {user_id}: {e}")
    
    if game_id in shared.multiplayer_games:
        del shared.multiplayer_games[game_id]
    
    game_collection.delete_one({"game_id": game_id})

async def handle_cancel_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id = query.data.split('_', 1)
    
    game = await get_game_data(game_id)
    if not game:
        await query.answer("Game not found or expired!")
        return
    
    if user_id not in game["batters"] and user_id not in game["bowlers"]:
        await query.answer("You can't cancel - not your turn!")
        return
    
    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=f"🛑 Game cancelled by a player!"
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
            await context.bot.send_message(
                chat_id=uid,
                text="🛑 Game has been cancelled!"
            )
        except Exception as e:
            logger.error(f"Error notifying player {uid} about cancellation: {e}")
    
    if game_id in shared.multiplayer_games:
        del shared.multiplayer_games[game_id]
    
    game_collection.delete_one({"game_id": game_id})
    
    await query.answer("Game cancelled!")

def get_multiplayer_handlers():
    return [
        CommandHandler("multiplayer", multiplayer),
        CallbackQueryHandler(handle_join_button, pattern=r"^join_(batter|bowler)_"),
        CallbackQueryHandler(handle_remove_button, pattern=r"^remove_"),
        CallbackQueryHandler(handle_play_button, pattern=r"^play_"),
        CallbackQueryHandler(handle_cancel_button, pattern=r"^cancel_")
    ]