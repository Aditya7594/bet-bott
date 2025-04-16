from multiprocessing import context
from pymongo import MongoClient
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from datetime import datetime, timedelta
import time
import pytz
import asyncio
from datetime import datetime, timedelta
from telegram import User
from functools import lru_cache

from functools import lru_cache

@lru_cache(maxsize=512)
def get_user_name_cached_sync(user_id: int, fallback: str = "Player") -> str:
    return fallback  # fallback if async call fails

async def get_user_name_cached(user_id, context):
    try:
        chat = await context.bot.get_chat(user_id)
        return chat.first_name
    except:
        return get_user_name_cached_sync(user_id)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
user_collection = db["users"]
game_collection = db["games"]
achievements_collection = db["achievements"]  # Add this line
multiplayer_game_collection = db["multiplayer_games"]

# Game state
cricket_games = {}
reminder_sent = {}
game_activity = {}
multiplayer_games = {}

ACHIEVEMENT_CATEGORIES = [
    "Batter", "Bowler", "Game", 
    "Matches", "Accuracy", "Streaks", 
    "Special"
]

ACHIEVEMENTS = {
    "Batter": [
        {"id": "first_run", "name": "First Run", "description": "Score your first run", "requirement": {"type": "runs", "value": 1}},
        {"id": "five_runs", "name": "Getting Started", "description": "Score 5 runs in total", "requirement": {"type": "runs", "value": 5}},
        {"id": "ten_runs", "name": "First Steps", "description": "Score 10 runs in total", "requirement": {"type": "runs", "value": 10}},
        {"id": "twenty_runs", "name": "Building Form", "description": "Score 20 runs in total", "requirement": {"type": "runs", "value": 20}},
        {"id": "quarter_century", "name": "Quarter Century", "description": "Score 25 runs in total", "requirement": {"type": "runs", "value": 25}},
        {"id": "forty_runs", "name": "Solid Innings", "description": "Score 40 runs in total", "requirement": {"type": "runs", "value": 40}},
        {"id": "half_century", "name": "Half Century", "description": "Score 50 runs in total", "requirement": {"type": "runs", "value": 50}},
        {"id": "seventy_runs", "name": "Well Played", "description": "Score 70 runs in total", "requirement": {"type": "runs", "value": 70}},
        {"id": "century", "name": "Century", "description": "Score 100 runs in total", "requirement": {"type": "runs", "value": 100}},
        {"id": "one_fifty", "name": "One-Fifty", "description": "Score 150 runs in total", "requirement": {"type": "runs", "value": 150}},
        {"id": "double_century", "name": "Double Century", "description": "Score 200 runs in total", "requirement": {"type": "runs", "value": 200}},
        {"id": "triple_century", "name": "Triple Century", "description": "Score 300 runs in total", "requirement": {"type": "runs", "value": 300}},
        {"id": "four_hundred", "name": "Four Hundred Club", "description": "Score 400 runs in total", "requirement": {"type": "runs", "value": 400}},
        {"id": "run_machine", "name": "Run Machine", "description": "Score 500 runs in total", "requirement": {"type": "runs", "value": 500}},
        {"id": "seven_fifty", "name": "Run Accumulator", "description": "Score 750 runs in total", "requirement": {"type": "runs", "value": 750}},
        {"id": "batting_legend", "name": "Batting Legend", "description": "Score 1000 runs in total", "requirement": {"type": "runs", "value": 1000}},
        {"id": "batting_immortal", "name": "Batting Immortal", "description": "Score 2000 runs in total", "requirement": {"type": "runs", "value": 2000}},
    ],
    "Bowler": [
        {"id": "first_wicket", "name": "First Wicket", "description": "Take your first wicket", "requirement": {"type": "wickets", "value": 1}},
        {"id": "third_wicket", "name": "Getting Started", "description": "Take 3 wickets in total", "requirement": {"type": "wickets", "value": 3}},
        {"id": "five_wickets", "name": "Five Wicket Haul", "description": "Take 5 wickets in total", "requirement": {"type": "wickets", "value": 5}},
        {"id": "seven_wickets", "name": "Seven Heaven", "description": "Take 7 wickets in total", "requirement": {"type": "wickets", "value": 7}},
        {"id": "ten_wickets", "name": "Ten Wicket Club", "description": "Take 10 wickets in total", "requirement": {"type": "wickets", "value": 10}},
        {"id": "fifteen_wickets", "name": "Frequent Striker", "description": "Take 15 wickets in total", "requirement": {"type": "wickets", "value": 15}},
        {"id": "twenty_wickets", "name": "Regular Wicket Taker", "description": "Take 20 wickets in total", "requirement": {"type": "wickets", "value": 20}},
        {"id": "wicket_master", "name": "Wicket Master", "description": "Take 25 wickets in total", "requirement": {"type": "wickets", "value": 25}},
        {"id": "thirty_wickets", "name": "Reliable Bowler", "description": "Take 30 wickets in total", "requirement": {"type": "wickets", "value": 30}},
        {"id": "wicket_specialist", "name": "Wicket Specialist", "description": "Take 35 wickets in total", "requirement": {"type": "wickets", "value": 35}},
        {"id": "forty_wickets", "name": "Bowling Expert", "description": "Take 40 wickets in total", "requirement": {"type": "wickets", "value": 40}},
        {"id": "bowling_legend", "name": "Bowling Legend", "description": "Take 50 wickets in total", "requirement": {"type": "wickets", "value": 50}},
        {"id": "seventy_five_wickets", "name": "Elite Bowler", "description": "Take 75 wickets in total", "requirement": {"type": "wickets", "value": 75}},
        {"id": "bowling_immortal", "name": "Bowling Immortal", "description": "Take 100 wickets in total", "requirement": {"type": "wickets", "value": 100}},
    ],
    "Game": [
        {"id": "first_win", "name": "First Victory", "description": "Win your first game", "requirement": {"type": "wins", "value": 1}},
        {"id": "three_wins", "name": "Winning Ways", "description": "Win 3 games", "requirement": {"type": "wins", "value": 3}},
        {"id": "five_wins", "name": "Winner's Circle", "description": "Win 5 games", "requirement": {"type": "wins", "value": 5}},
        {"id": "seven_wins", "name": "Consistent Winner", "description": "Win 7 games", "requirement": {"type": "wins", "value": 7}},
        {"id": "ten_wins", "name": "Champion", "description": "Win 10 games", "requirement": {"type": "wins", "value": 10}},
        {"id": "fifteen_wins", "name": "Rising Champion", "description": "Win 15 games", "requirement": {"type": "wins", "value": 15}},
        {"id": "twenty_wins", "name": "Cricket Master", "description": "Win 20 games", "requirement": {"type": "wins", "value": 20}},
        {"id": "twenty_five_wins", "name": "Cricket Commander", "description": "Win 25 games", "requirement": {"type": "wins", "value": 25}},
        {"id": "thirty_wins", "name": "Dominator", "description": "Win 30 games", "requirement": {"type": "wins", "value": 30}},
        {"id": "forty_wins", "name": "Game Controller", "description": "Win 40 games", "requirement": {"type": "wins", "value": 40}},
        {"id": "fifty_wins", "name": "Legendary Player", "description": "Win 50 games", "requirement": {"type": "wins", "value": 50}},
        {"id": "seventy_five_wins", "name": "Match Winner", "description": "Win 75 games", "requirement": {"type": "wins", "value": 75}},
        {"id": "hundred_wins", "name": "Cricket God", "description": "Win 100 games", "requirement": {"type": "wins", "value": 100}},
    ],
    "Matches": [
        {"id": "first_match", "name": "Cricket Debut", "description": "Play your first match", "requirement": {"type": "matches", "value": 1}},
        {"id": "three_matches", "name": "Getting Started", "description": "Play 3 matches", "requirement": {"type": "matches", "value": 3}},
        {"id": "five_matches", "name": "Regular Player", "description": "Play 5 matches", "requirement": {"type": "matches", "value": 5}},
        {"id": "seven_matches", "name": "Experienced Player", "description": "Play 7 matches", "requirement": {"type": "matches", "value": 7}},
        {"id": "ten_matches", "name": "Cricket Enthusiast", "description": "Play 10 matches", "requirement": {"type": "matches", "value": 10}},
        {"id": "fifteen_matches", "name": "Cricket Devotee", "description": "Play 15 matches", "requirement": {"type": "matches", "value": 15}},
        {"id": "twenty_matches", "name": "Cricket Addict", "description": "Play 20 matches", "requirement": {"type": "matches", "value": 20}},
        {"id": "twenty_five_matches", "name": "Cricket Specialist", "description": "Play 25 matches", "requirement": {"type": "matches", "value": 25}},
        {"id": "thirty_matches", "name": "Cricket Professional", "description": "Play 30 matches", "requirement": {"type": "matches", "value": 30}},
        {"id": "forty_matches", "name": "Cricket Expert", "description": "Play 40 matches", "requirement": {"type": "matches", "value": 40}},
        {"id": "fifty_matches", "name": "Cricket Veteran", "description": "Play 50 matches", "requirement": {"type": "matches", "value": 50}},
        {"id": "seventy_five_matches", "name": "Cricket Master", "description": "Play 75 matches", "requirement": {"type": "matches", "value": 75}},
        {"id": "hundred_matches", "name": "Cricket Legend", "description": "Play 100 matches", "requirement": {"type": "matches", "value": 100}},
    ],
    "Accuracy": [
        {"id": "improving", "name": "Improving", "description": "Achieve 15% win rate", "requirement": {"type": "accuracy", "value": 15}},
        {"id": "developing", "name": "Developing", "description": "Achieve 20% win rate", "requirement": {"type": "accuracy", "value": 20}},
        {"id": "rising_star", "name": "Rising Star", "description": "Achieve 25% win rate", "requirement": {"type": "accuracy", "value": 25}},
        {"id": "promising", "name": "Promising Player", "description": "Achieve 30% win rate", "requirement": {"type": "accuracy", "value": 30}},
        {"id": "talent_emerging", "name": "Talent Emerging", "description": "Achieve 35% win rate", "requirement": {"type": "accuracy", "value": 35}},
        {"id": "consistent_player", "name": "Consistent Player", "description": "Achieve 40% win rate", "requirement": {"type": "accuracy", "value": 40}},
        {"id": "reliable_winner", "name": "Reliable Winner", "description": "Achieve 45% win rate", "requirement": {"type": "accuracy", "value": 45}},
        {"id": "star_player", "name": "Star Player", "description": "Achieve 50% win rate", "requirement": {"type": "accuracy", "value": 50}},
        {"id": "formidable", "name": "Formidable Player", "description": "Achieve 55% win rate", "requirement": {"type": "accuracy", "value": 55}},
        {"id": "elite_player", "name": "Elite Player", "description": "Achieve 60% win rate", "requirement": {"type": "accuracy", "value": 60}},
        {"id": "outstanding", "name": "Outstanding Player", "description": "Achieve 65% win rate", "requirement": {"type": "accuracy", "value": 65}},
        {"id": "exceptional", "name": "Exceptional Player", "description": "Achieve 70% win rate", "requirement": {"type": "accuracy", "value": 70}},
        {"id": "world_class", "name": "World Class", "description": "Achieve 75% win rate", "requirement": {"type": "accuracy", "value": 75}},
        {"id": "master_tactician", "name": "Master Tactician", "description": "Achieve 80% win rate", "requirement": {"type": "accuracy", "value": 80}},
        {"id": "legendary_status", "name": "Legendary Status", "description": "Achieve 85% win rate", "requirement": {"type": "accuracy", "value": 85}},
    ],
    "Streaks": [
        {"id": "winning_streak_2", "name": "On a Roll", "description": "Win 2 games in a row", "requirement": {"type": "streak", "value": 2}},
        {"id": "winning_streak_3", "name": "Hot Streak", "description": "Win 3 games in a row", "requirement": {"type": "streak", "value": 3}},
        {"id": "winning_streak_4", "name": "Unrelenting", "description": "Win 4 games in a row", "requirement": {"type": "streak", "value": 4}},
        {"id": "winning_streak_5", "name": "Unstoppable", "description": "Win 5 games in a row", "requirement": {"type": "streak", "value": 5}},
        {"id": "winning_streak_6", "name": "Winning Machine", "description": "Win 6 games in a row", "requirement": {"type": "streak", "value": 6}},
        {"id": "winning_streak_7", "name": "Domination", "description": "Win 7 games in a row", "requirement": {"type": "streak", "value": 7}},
        {"id": "winning_streak_8", "name": "Invincible", "description": "Win 8 games in a row", "requirement": {"type": "streak", "value": 8}},
        {"id": "winning_streak_9", "name": "Unbeatable", "description": "Win 9 games in a row", "requirement": {"type": "streak", "value": 9}},
        {"id": "winning_streak_10", "name": "Legendary Streak", "description": "Win 10 games in a row", "requirement": {"type": "streak", "value": 10}},
    ],
    "Special": [
        {"id": "perfect_match", "name": "Perfect Match", "description": "Win without conceding a wicket", "requirement": {"type": "special", "value": "perfect_match"}},
        {"id": "comeback_king", "name": "Comeback King", "description": "Win after being 10+ runs behind", "requirement": {"type": "special", "value": "comeback"}},
        {"id": "tied_match", "name": "Nail-Biter", "description": "Play a tied match", "requirement": {"type": "special", "value": "tie"}},
        {"id": "hat_trick", "name": "Hat-Trick", "description": "Take 3 wickets in 3 consecutive balls", "requirement": {"type": "special", "value": "hat_trick"}},
        {"id": "last_ball_victory", "name": "Last Ball Hero", "description": "Win a match on the last ball", "requirement": {"type": "special", "value": "last_ball_win"}},
        {"id": "golden_duck", "name": "Golden Duck Hunter", "description": "Take a wicket on the first ball of an over", "requirement": {"type": "special", "value": "golden_duck"}},
        {"id": "perfect_over", "name": "Perfect Over", "description": "Bowl an over without conceding any runs", "requirement": {"type": "special", "value": "perfect_over"}},
        {"id": "boundary_king", "name": "Boundary King", "description": "Score 5 boundaries in a single match", "requirement": {"type": "special", "value": "boundary_king"}},
        {"id": "maiden_over", "name": "Maiden Over", "description": "Bowl a full over without conceding any runs", "requirement": {"type": "special", "value": "maiden_over"}},
        {"id": "super_over_hero", "name": "Super Over Hero", "description": "Win a match in a super over", "requirement": {"type": "special", "value": "super_over_win"}},
        {"id": "death_over_specialist", "name": "Death Over Specialist", "description": "Successfully defend 10 or fewer runs in the final over", "requirement": {"type": "special", "value": "death_over_defend"}},
        {"id": "six_machine", "name": "Six Machine", "description": "Hit 3 sixes in a single match", "requirement": {"type": "special", "value": "six_machine"}},
    ]
}

async def check_user_started_bot(update: Update, context: CallbackContext) -> bool:
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

async def chat_cricket(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if update.effective_chat.type == "private":
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ This command can only be used in group chats!")
        return
    
    if not await check_user_started_bot(update, context):
        return
    
    max_overs = 100  
    max_wickets = 1 
    if context.args:
        try:
            if len(context.args) >= 1:
                max_overs = int(context.args[0])
            if len(context.args) >= 2:
                max_wickets = int(context.args[1])
            if max_overs < 1:
                max_overs = 1
            if max_wickets < 1:
                max_wickets = 1
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Invalid parameters! Format: /chatcricket [overs] [wickets]")
            return
    
    game_id = f"{chat_id}_{int(time.time())}"
    cricket_games[game_id] = {
        "player1": user.id,
        "player2": None,
        "score1": 0,
        "score2": 0,
        "message_id": {},
        "over": 0,
        "ball": 0,
        "batter": None,
        "bowler": None,
        "toss_winner": None,
        "innings": 1,
        "wickets1": 0,
        "wickets2": 0,
        "current_players": {},
        "batter_choice": None,
        "bowler_choice": None,
        "target": None,
        "group_chat_id": chat_id,
        "match_details": [],
        "wickets": 0,
        "max_wickets": max_wickets,
        "max_overs": max_overs,
        "spectators": set(),
        "last_move": datetime.utcnow(),
        "last_reminder": None
    }
    
    game_desc = f"🏏 *Cricket Game Started!*\n\n"
    game_desc += f"Started by: {user.first_name}\n"
    game_desc += f"Format: {max_overs} over{'s' if max_overs > 1 else ''}, {max_wickets} wicket{'s' if max_wickets > 1 else ''}\n\n"
    game_desc += f"• To join, click \"Join Game\"\n"
    game_desc += f"• To watch, click \"Watch Game\"\n"
    game_desc += f"• For the best experience, open the bot directly"
    
    bot_username = (await context.bot.get_me()).username
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Game", callback_data=f"join_{game_id}")],
        [InlineKeyboardButton("Watch Game", callback_data=f"watch_{game_id}")],
        [InlineKeyboardButton("🎮 Open Cricket Bot", url=f"https://t.me/{bot_username}")]
    ])
    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=game_desc,
        reply_markup=keyboard,
        parse_mode="Markdown")
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.message_id)

def update_game_activity(game_id):
    game_activity[game_id] = datetime.utcnow()
    if game_id in cricket_games:
        cricket_games[game_id]["last_move"] = datetime.utcnow()

async def update_game_interface(game_id: str, context: CallbackContext, text: str = None):
    if game_id not in cricket_games:
        return

    game = cricket_games[game_id]
    if not text:
        try:
            batter_name = (await get_user_name_cached(game["batter"], context))
            bowler_name = (await get_user_name_cached(game["bowler"], context))
        except Exception:
            await context.bot.send_message(
                chat_id=game["group_chat_id"],
                text="⚠️ Error retrieving player information. Please try again.")
            return

        score = game['score1'] if game['innings'] == 1 else game['score2']
        target = game['target'] if game['innings'] == 2 else None
        spectator_count = len(game["spectators"])
        
        spectator_text = f"👁️ {spectator_count}" if spectator_count > 0 else ""
        
        text = (
            f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
            f"🔸 Batting: {batter_name}\n"
            f"🔹 Bowling: {bowler_name}\n"
            f"📊 Score: {score}/{game['wickets']}"
        )
        
        if game['innings'] == 2:
            text += f" (Target: {game['target']})"
        
        text += "\n\n"

        if game["batter_choice"] is None:
            text += f"⚡ {batter_name}, choose a number (1-6):"
        else:
            text += f"⚡ {bowler_name}, choose a number (1-6):"

    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_id}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_id}")])

    recipients = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in recipients:
        try:
            if player_id not in game["message_id"]:
                msg = await context.bot.send_message(
                    chat_id=player_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard) if player_id not in game["spectators"] else None,
                    parse_mode="Markdown"
                )
                game["message_id"][player_id] = msg.message_id
            else:
                await context.bot.edit_message_text(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id),
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard) if player_id not in game["spectators"] else None,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error updating game interface for {player_id}: {e}")

async def handle_join_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id = query.data.split('_', 1)  # Modified to handle the new game_id format
    
    if not await check_user_started_bot(update, context):
        return
    
    if game_id not in cricket_games:
        await query.answer("Game not found or expired!")
        return

    game = cricket_games[game_id]
    
    if user_id == game["player1"]:
        await query.answer("You can't join your own game!")
        return

    if game["player2"]:
        await query.answer("Game full!")
        return

    game["player2"] = user_id
    update_game_activity(game_id)

    
    bot_username = (await context.bot.get_me()).username
    keyboard = [[InlineKeyboardButton("🎮 Open Cricket Game", url=f"https://t.me/{bot_username}")]]

    
    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=f"🎉 {query.from_user.first_name} joined the game!\n\n"
                 f"Players should open the bot to continue the game:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error sending join confirmation to group chat: {e}")
        await query.answer("Error sending join confirmation!")
        return
    
    toss_keyboard = [[
        InlineKeyboardButton("Heads", callback_data=f"toss_{game_id}_heads"),
        InlineKeyboardButton("Tails", callback_data=f"toss_{game_id}_tails")
    ]]
    
    for player_id in [game["player1"], game["player2"]]:
        try:
            msg = await context.bot.send_message(
                chat_id=player_id,
                text="⚡ Toss Time!",
                reply_markup=InlineKeyboardMarkup(toss_keyboard))
            game["message_id"][player_id] = msg.message_id
        except Exception as e:
            logger.error(f"Error sending toss message to {player_id}: {e}")

    # ✅ Save the active game to MongoDB so /c or /chat works
    try:
        db['cricket_games'].update_one(
            {"_id": game_id},
            {
                "$set": {
                    "player1": str(game["player1"]),
                    "player2": str(game["player2"]),
                    "active": True,
                    "group_chat_id": game["group_chat_id"],
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        logger.info(f"Cricket game {game_id} saved as active in MongoDB")
    except Exception as e:
        logger.error(f"Error saving active cricket game to MongoDB: {e}")

async def handle_watch_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id = query.data.split('_', 1)  # Modified to handle the new game_id format

    if not await check_user_started_bot(update, context):
        return

    if game_id not in cricket_games:
        await query.answer("Game not found or expired!")
        return

    game = cricket_games[game_id]
    
    if user_id in [game["player1"], game["player2"]]:
        await query.answer("You're already playing in this game!")
        return
    
    game["spectators"].add(user_id)
    
    player1_name = (await get_user_name_cached(game["player1"], context))
    player2_name = "Waiting for opponent" if not game["player2"] else (await get_user_name_cached(game["player2"], context))
    
    bot_username = (await context.bot.get_me()).username
    keyboard = [[InlineKeyboardButton("🎮 Open Cricket Game", url=f"https://t.me/{bot_username}")]]
    
    await query.message.reply_text(
        f"👁️ You're now watching the cricket match!\n"
        f"🧑 Player 1: {player1_name}\n"
        f"🧑 Player 2: {player2_name}\n\n"
        f"Open the bot to view live match updates:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    if game["player2"] and "batter" in game and game["batter"]:
        await update_game_interface(game_id, context)

async def toss_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data_parts = query.data.split('_')
    choice = data_parts[-1]
    game_id = '_'.join(data_parts[1:-1])

    
    if not await check_user_started_bot(update, context):
        return
    
    logger.info(f"Cricket Game - Toss Button: User {user_id} chose {choice} for game {game_id}")
    logger.info(f"TOSS: Received game_id={game_id}, Active games={list(cricket_games.keys())}")


    if game_id not in cricket_games:
        logger.warning(f"Cricket Game - Toss Button: Game {game_id} not found")
        await query.answer("Game expired!")
        return

    game = cricket_games[game_id]
    if game["toss_winner"]:
        logger.info(f"Cricket Game - Toss Button: Toss already completed for game {game_id}")
        await query.answer("Toss done!")
        return

    toss_result = random.choice(['heads', 'tails'])
    game["toss_winner"] = user_id if choice == toss_result else game["player2"] if user_id == game["player1"] else game["player1"]
    
    logger.info(f"Cricket Game - Toss Button: Toss result was {toss_result}, winner is {game['toss_winner']}")

    winner_name = (await get_user_name_cached(game["toss_winner"], context))
    keyboard = [[
        InlineKeyboardButton("🏏 Bat", callback_data=f"choose_{game_id}_bat"),
        InlineKeyboardButton("🎯 Bowl", callback_data=f"choose_{game_id}_bowl")
    ]]

    for player_id in [game["player1"], game["player2"]]:
        try:
            await context.bot.edit_message_text(
                chat_id=player_id,
                message_id=game["message_id"][player_id],
                text=f"{winner_name} won toss!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error updating toss result for player {player_id}: {e}")

async def choose_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data_parts = query.data.split('_')
    choice = data_parts[-1]
    game_id = '_'.join(data_parts[1:-1]) # Modified to handle the new game_id format
    
    if not await check_user_started_bot(update, context):
        return
    
    logger.info(f"Cricket Game - Choose Button: User {user_id} chose to {choice} for game {game_id}")

    if game_id not in cricket_games:
        logger.warning(f"Cricket Game - Choose Button: Game {game_id} not found")
        await query.answer("Game expired!")
        return

    game = cricket_games[game_id]
    if user_id != game["toss_winner"]:
        logger.info(f"Cricket Game - Choose Button: User {user_id} tried to choose when not toss winner")
        await query.answer("Not your choice!")
        return

    if choice == "bat":
        batter, bowler = user_id, game["player2"] if user_id == game["player1"] else game["player1"]
    else:
        bowler, batter = user_id, game["player2"] if user_id == game["player1"] else game["player1"]

    game.update({
        "batter": batter,
        "bowler": bowler,
        "current_players": {"batter": batter, "bowler": bowler}
    })
    
    logger.info(f"Cricket Game - Choose Button: Game {game_id} setup - Batter: {batter}, Bowler: {bowler}")

    await update_game_interface(game_id, context)

async def play_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    parts = query.data.split('_')
    number = int(parts[-1])
    game_id = '_'.join(parts[1:-1])  # Handles game_id with underscores

    if not await check_user_started_bot(update, context):
        return

    logger.info(f"Cricket Game - Play Button: User {user_id} chose number {number} for game {game_id}")

    if game_id not in cricket_games:
        logger.warning(f"Cricket Game - Play Button: Game {game_id} not found")
        await query.answer("Game expired!")
        return

    game = cricket_games[game_id]
    update_game_activity(game_id)

    # Batter's move
    if user_id == game["current_players"]["batter"] and game["batter_choice"] is None:
        game["batter_choice"] = number
        logger.info(f"Cricket Game - Play Button: Batter {user_id} chose {number}")
        await query.answer(f"Your choice: {number}")

        batter_name = (await get_user_name_cached(game["batter"], context))
        bowler_name = (await get_user_name_cached(game["bowler"], context))
        score = game['score1'] if game['innings'] == 1 else game['score2']
        spectator_count = len(game["spectators"])
        spectator_text = f"👁️ {spectator_count}" if spectator_count > 0 else ""

        text = (
            f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
            f"🔸 Batting: {batter_name}\n"
            f"🔹 Bowling: {bowler_name}\n"
            f"📊 Score: {score}/{game['wickets']}"
        )

        if game['innings'] == 2:
            text += f" (Target: {game['target']})"

        text += "\n\n⚡ Batter has chosen. Now bowler's turn."

        # Update spectators
        for spectator_id in game["spectators"]:
            try:
                await context.bot.edit_message_text(
                    chat_id=spectator_id,
                    message_id=game["message_id"].get(spectator_id),
                    text=text
                )
            except Exception as e:
                logger.error(f"Error updating for spectator {spectator_id}: {e}")

        # Update players
        for player_id in [game["player1"], game["player2"]]:
            player_text = text
            if player_id == game["current_players"]["batter"]:
                player_text += f"\n\nYou chose: {number}"
            else:
                player_text += f"\n\n⚡ {bowler_name}, choose a number (1-6):"

            keyboard = []
            if player_id == game["current_players"]["bowler"]:
                await asyncio.sleep(0.05)
                row = []
                for i in range(1, 7):
                    row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_id}_{i}"))
                    if len(row) == 3:
                        keyboard.append(row)
                        row = []
                keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_id}")])

            try:
                await context.bot.edit_message_text(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id),
                    text=player_text,
                    reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
                )
            except Exception as e:
                logger.error(f"Error updating for player {player_id}: {e}")

    # Bowler's move
    elif user_id == game["current_players"]["bowler"] and game["bowler_choice"] is None:
        batter_choice = game.get("batter_choice")
        bowler_choice = number

        if batter_choice is None:
            logger.warning(f"Batter choice was None when bowler moved (game_id={game_id})")
            await query.answer("Batter hasn't played yet!")
            return

        game["bowler_choice"] = number
        logger.info(f"Cricket Game - Play Button: Bowler {user_id} chose {number}")
        await query.answer(f"Your choice: {number}")

        game["batter_choice"] = None
        game["bowler_choice"] = None

        batter_name = (await get_user_name_cached(game["batter"], context))
        bowler_name = (await get_user_name_cached(game["bowler"], context))
        score = game['score1'] if game['innings'] == 1 else game['score2']
        target = game['target'] if game['innings'] == 2 else None
        spectator_count = len(game["spectators"])
        spectator_text = f"👁️ {spectator_count}" if spectator_count > 0 else ""

        if batter_choice == bowler_choice:
            result_text = f"🎯 Ball Result: WICKET!\nBatter: {batter_choice} | Bowler: {bowler_choice}"
            game["wickets"] += 1
            game["match_details"].append((game["over"], game["ball"], 0, True))

            text = (
                f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
                f"🔸 Batting: {batter_name}\n"
                f"🔹 Bowling: {bowler_name}\n"
                f"📊 Score: {score}/{game['wickets']}\n\n"
                f"{result_text}"
            )

            for participant_id in list(game["spectators"]) + [game["player1"], game["player2"]]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=participant_id,
                        message_id=game["message_id"].get(participant_id),
                        text=text
                    )
                except Exception as e:
                    logger.error(f"Error updating participant {participant_id}: {e}")

            await handle_wicket(game_id, context)
            return

        else:
            runs = batter_choice
            result_text = f"🎯 Ball Result: {runs} RUNS!\nBatter: {batter_choice} | Bowler: {bowler_choice}"
            if isinstance(runs, int):
                if game["innings"] == 1:
                    game["score1"] += runs
                else:
                    game["score2"] += runs
            else:
                logger.warning(f"Invalid run value (None): game_id={game_id}, user={user_id}")
                await query.answer("An error occurred with the run value.")
                return

            game["match_details"].append((game["over"], game["ball"], runs, False))
            game["ball"] += 1
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0

            if game["innings"] == 2 and game["score2"] >= game["target"]:
                text = (
                    f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
                    f"🔸 Batting: {batter_name}\n"
                    f"🔹 Bowling: {bowler_name}\n"
                    f"📊 Score: {game['score2']}/{game['wickets']}\n\n"
                    f"{result_text}"
                )
                for pid in list(game["spectators"]) + [game["player1"], game["player2"]]:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=pid,
                            message_id=game["message_id"].get(pid),
                            text=text
                        )
                    except Exception as e:
                        logger.error(f"Error updating participant {pid}: {e}")
                await declare_winner(game_id, context)
                return

            elif game["over"] >= game["max_overs"]:
                text = (
                    f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
                    f"🔸 Batting: {batter_name}\n"
                    f"🔹 Bowling: {bowler_name}\n"
                    f"📊 Score: {score}/{game['wickets']}\n\n"
                    f"{result_text}"
                )
                for pid in list(game["spectators"]) + [game["player1"], game["player2"]]:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=pid,
                            message_id=game["message_id"].get(pid),
                            text=text
                        )
                    except Exception as e:
                        logger.error(f"Error updating participant {pid}: {e}")
                await end_innings(game_id, context)
                return

        # Update for next ball
        score = game['score1'] if game['innings'] == 1 else game['score2']
        text = (
            f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
            f"🔸 Batting: {batter_name}\n"
            f"🔹 Bowling: {bowler_name}\n"
            f"📊 Score: {score}/{game['wickets']}"
        )

        if game['innings'] == 2:
            text += f" (Target: {game['target']})"

        text += f"\n\n{result_text}\n\n⚡ {batter_name}, choose a number (1-6):"

        keyboard = []
        row = []
        for i in range(1, 7):
            row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_id}_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_id}")])

        for pid in list(game["spectators"]) + [game["player1"], game["player2"]]:
            try:
                participant_keyboard = InlineKeyboardMarkup(keyboard) if pid == game["current_players"]["batter"] else None
                await context.bot.edit_message_text(
                    chat_id=pid,
                    message_id=game["message_id"].get(pid),
                    text=text,
                    reply_markup=participant_keyboard
                )
            except Exception as e:
                logger.error(f"Error updating participant {pid}: {e}")

    else:
        logger.info(f"Cricket Game - Play Button: User {user_id} tried to play out of turn")
        await query.answer("Not your turn!")

async def handle_wicket(game_id: str, context: CallbackContext) -> None:
    game = cricket_games[game_id]
    
    if game["innings"] == 1:
       game["wickets1"] = game["wickets"]
    else:
       game["wickets2"] = game["wickets"]

    
    if game['wickets'] >= game['max_wickets']:
        await end_innings(game_id, context)
        return
    
    # Reset for next ball
    game["ball"] += 1
    if game["ball"] == 6:
        game["over"] += 1
        game["ball"] = 0
    
    # Continue game with next ball
    await update_game_interface(game_id, context)

async def end_innings(game_id: str, context: CallbackContext) -> None:
    game = cricket_games[game_id]
    
    if game["innings"] == 1:
        # Set target for second innings
        game["target"] = game["score1"] + 1
        game["innings"] = 2
        game["over"] = 0
        game["ball"] = 0
        game["wickets"] = 0
        
        # Swap batter and bowler
        temp_batter = game["batter"]
        game["batter"] = game["bowler"]
        game["bowler"] = temp_batter
        game["current_players"] = {"batter": game["batter"], "bowler": game["bowler"]}
        
        # Update statistics for both players
        user1_id = game["player1"]
        user2_id = game["player2"]
        
        user_collection.update_one(
            {"user_id": str(user1_id)},
            {"$inc": {"stats.matches": 1, "stats.runs": game["score1"]}},
            upsert=True
        )
        
        user_collection.update_one(
            {"user_id": str(user2_id)},
            {"$inc": {"stats.matches": 1, "stats.runs": game["score2"]}},
            upsert=True
        )
        
        # Check for achievements after first innings
        await check_achievements(user1_id, context)
        await check_achievements(user2_id, context)
        
        # Notify all players of innings change
        batter_name = (await get_user_name_cached(game["batter"], context))
        bowler_name = (await get_user_name_cached(game["bowler"], context))
        
        text = (
            f"🏏 First Innings Complete!\n\n"
            f"Score: {game['score1']}/{game['max_wickets']} in {game['over']}.{game['ball']} overs\n\n"
            f"Second Innings:\n"
            f"🔸 Batting: {batter_name}\n"
            f"🔹 Bowling: {bowler_name}\n"
            f"Target: {game['target']} runs"
        )
        
        for participant_id in list(game["spectators"]) + [game["player1"], game["player2"]]:
            try:
                await context.bot.edit_message_text(
                    chat_id=participant_id,
                    message_id=game["message_id"].get(participant_id),
                    text=text
                )
            except Exception as e:
                print(f"Error updating participant {participant_id}: {e}")
        
        # Wait a moment before starting second innings
        await asyncio.sleep(0.1)
        
        # Start second innings
        await update_game_interface(game_id, context)
    else:
        # End of match
        await declare_winner(game_id, context)

async def declare_winner(game_id: str, context: CallbackContext):
    if game_id not in cricket_games:
        return

    game = cricket_games[game_id]

    # Player name fallback
    try:
        p1 = (await get_user_name_cached(game["player1"], context))
        p2 = (await get_user_name_cached(game["player2"], context))
    except Exception as e:
        logger.error(f"Error retrieving player names: {e}")
        p1 = "Player 1"
        p2 = "Player 2"

    winner_id = None
    loser_id = None

    # Decide winner
    if game["score1"] == game["score2"]:
        result = "🤝 Match Drawn!"
        await check_special_achievement(game_id, "tie", context)
    elif game["innings"] == 2:
        if game["score2"] >= game["target"]:
            winner_id = game["batter"]
            loser_id = game["bowler"]
            try:
                winner = (await get_user_name_cached(winner_id, context))
            except:
                winner = "Player"
            result = f"🏅 {winner} won by {game['max_wickets'] - game['wickets']} wicket(s)!"
            if game["wickets"] == 0:
                await check_special_achievement(game_id, "perfect_match", context, winner_id)
        else:
            winner_id = game["bowler"]
            loser_id = game["batter"]
            try:
                winner = (await get_user_name_cached(winner_id, context))
            except:
                winner = "Player"
            diff = game["target"] - game["score2"] - 1
            result = f"🏅 {winner} won by {diff} runs!"
    else:
        result = "Match ended unexpectedly!"

    # Accurate name-score mapping
    first_batter = game["player1"] if game["batter"] != game["player1"] else game["player2"]
    second_batter = game["batter"]
    try:
        name1 = (await get_user_name_cached(first_batter, context))
    except:
        name1 = "Player 1"
    try:
        name2 = (await get_user_name_cached(second_batter, context))
    except:
        name2 = "Player 2"

    score_summary = (
        f"🧑 {name1}: {game['score1']} runs\n"
        f"🧑 {name2}: {game['score2']} runs\n"
    )

    # Add wickets to summary
    wickets_summary = f"🎯 Wickets: {game['wickets']}/{game['max_wickets']}\n"

    result_message = (
        f"🏆 *GAME OVER!*\n\n"
        f"📜 *Match Summary:*\n"
        f"{score_summary}"
        f"{wickets_summary}"
        f"{result}"
    )

    # Send result to group
    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=result_message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error sending result to group chat: {e}")

    # Send result to all players/spectators
    participants = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in participants:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=result_message,
                parse_mode="Markdown"
            )
            if player_id in game["message_id"]:
                await context.bot.delete_message(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id)
                )
        except Exception as e:
            logger.error(f"Error sending result to {player_id}: {e}")

    # Update stats in DB
    if winner_id and loser_id:
        winner_id_str = str(winner_id)
        loser_id_str = str(loser_id)

        winner_runs = game['score2'] if winner_id == game["batter"] else game['score1']
        loser_runs = game['score1'] if winner_id == game["batter"] else game['score2']

        if game["innings"] == 2:
            if winner_id == game["batter"]:
                wickets_taken_by_winner = game["wickets1"]
            else:
                wickets_taken_by_winner = game["wickets2"]
        else:
            wickets_taken_by_winner = 0

        # Update winner
        user_collection.update_one(
            {"user_id": winner_id_str},
            {"$inc": {
                "stats.wins": 1,
                "stats.runs": winner_runs,
                "stats.wickets": wickets_taken_by_winner,
                "stats.current_streak": 1
            },
            "$set": {"stats.last_result": "win"}},
            upsert=True
        )

        # Update loser
        user_collection.update_one(
            {"user_id": loser_id_str},
            {"$inc": {
                "stats.losses": 1,
                "stats.runs": loser_runs,
                "stats.wickets": 0
            },
            "$set": {
                "stats.current_streak": 0,
                "stats.last_result": "loss"
            }},
            upsert=True
        )

        # Check achievements after match ends
        await check_achievements(winner_id, context)
        await check_achievements(loser_id, context)

        # Save match history
        try:
            game_collection.insert_one({
                "timestamp": datetime.now(),
                "participants": [game["player1"], game["player2"]],
                "scores": {
                    "player1": game["score1"],
                    "player2": game["score2"]
                },
                "wickets": game["wickets"],
                "winner": winner_id_str,    
                "loser": loser_id_str,
                "result": result,
                "innings": game["innings"],
                "player1_opponent": game["player2"],
                "player2_opponent": game["player1"]
            })
        except Exception as e:
            logger.error(f"Error saving game history: {e}")

    # Clean up memory
    reminder_sent.pop(game_id, None)
    game_activity.pop(game_id, None)
    cricket_games.pop(game_id, None)
    try:
        db['cricket_games'].update_one(
            {"_id": game_id},
            {"$set": {"active": False}}
        )
        logger.info(f"Game {game_id} marked inactive in DB after completion.")
    except Exception as e:
        logger.error(f"Error updating game status in DB: {e}")

async def chat_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /chat <message>")
        return

    user = update.effective_user
    user_id = user.id
    message = " ".join(context.args)

    if not await check_user_started_bot(update, context):
        return

    active_game = None
    for game_id, game in cricket_games.items():
        if user_id in [game["player1"], game["player2"]] or user_id in game.get("spectators", set()):
            active_game = game
            break

    if not active_game:
        await update.message.reply_text("❌ You're not part of an active cricket game.")
        return

    sender_name = user.first_name or "Player"
    formatted_message = f"💬 {sender_name}: {message}"

    recipients = set([active_game["player1"], active_game["player2"]] + list(active_game.get("spectators", [])))
    message_ids = []

    # Send to all recipients privately and collect message_ids
    for uid in recipients:
        if uid != user_id:
            try:
                sent_msg = await context.bot.send_message(chat_id=uid, text=formatted_message)
                message_ids.append((uid, sent_msg.message_id))
            except Exception as e:
                logger.error(f"Couldn't send DM to {uid}: {e}")

    # Schedule deletion of command and DMs in background
    async def delete_later():
        await asyncio.sleep(10)
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except Exception as e:
            logger.error(f"Error deleting /chat command message: {e}")
        for uid, mid in message_ids:
            try:
                await context.bot.delete_message(chat_id=uid, message_id=mid)
            except Exception as e:
                logger.error(f"Error deleting DM message for {uid}: {e}")

    asyncio.create_task(delete_later())

async def game_chat(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /chat <message>")
        return
    
    user = update.effective_user
    message = " ".join(context.args)
    
    active_game = None
    for game_id, game in cricket_games.items():
        if user.id in [game["player1"], game["player2"]]:
            active_game = game
            break
    
    if not active_game:
        await update.message.reply_text("You are not in an active game.")
        return
    
    participants = active_game.get("participants", [])
    for participant_id in participants:
        try:
            await context.bot.send_message(
                chat_id=participant_id,
                text=f"💬 {user.first_name}: {message}"
            )
        except Exception as e:
            logger.error(f"Error sending chat message to {participant_id}: {e}")

async def game_history(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    try:
        history = list(game_collection.find(
            {"$or": [
                {"participants": {"$in": [user_id]}},
                {"player1_opponent": user_id},
                {"player2_opponent": user_id}
            ]},
            {"_id": 0}
        ).sort("timestamp", -1).limit(5))
        
        if not history:
            await update.message.reply_text("You haven't played any games yet!")
            return
        
        text = "📜 *Your Game History:*\n\n"
        for idx, game in enumerate(history, 1):
            timestamp_str = game.get('timestamp', datetime.now()).strftime("%Y-%m-%d %H:%M")
            
            participants = game.get('participants', [])
            opponent_id = None
            for participant in participants:
                if participant != user_id:
                    opponent_id = participant
                    break
            
            if not opponent_id:
                if game.get('player1_opponent') == user_id:
                    opponent_id = game.get('player1')
                elif game.get('player2_opponent') == user_id:
                    opponent_id = game.get('player2')
            
            opponent_name = "Unknown"
            if opponent_id:
                opponent_data = user_collection.find_one({"user_id": opponent_id})
                if opponent_data:
                    opponent_name = opponent_data.get('first_name', 'Unknown')
            
            scores = game.get('scores', {})
            user_score = scores.get('player1', 0) if user_id == game.get('participants', [])[0] else scores.get('player2', 0)
            opponent_score = scores.get('player2', 0) if user_id == game.get('participants', [])[0] else scores.get('player1', 0)
            
            text += f"*Game {idx}:*\n"
            text += f"📅 Date: {timestamp_str}\n"
            text += f"👤 Opponent: {opponent_name}\n"
            text += f"🏏 Your Score: {user_score}\n"
            text += f"🏏 Opponent Score: {opponent_score}\n"
            text += f"📝 Result: {game.get('result', 'No result')}\n\n"
        
        await update.message.reply_text(text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error retrieving game history: {e}")
        await update.message.reply_text("An error occurred while retrieving your game history. Please try again later.")

async def stats(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("You need to start the bot first!")
        return
    
    stats_data = user_collection.find_one({"user_id": user_id}, {"_id": 0, "stats": 1})
    if not stats_data or "stats" not in stats_data:
        await update.message.reply_text("No statistics available yet. Play some games to see your stats!")
        return
    
    stats = stats_data["stats"]
    games_played = stats.get('wins', 0) + stats.get('losses', 0)
    
    accuracy = 0
    if games_played > 0:
        accuracy = round((stats.get('wins', 0) / games_played) * 100)
    
    text = f"📊 *Your Statistics:*\n\n"
    text += f"🏏 *Games*\n"
    text += f"▫️ Played: {games_played}\n"
    text += f"▫️ Wins: {stats.get('wins', 0)}\n"
    text += f"▫️ Losses: {stats.get('losses', 0)}\n"
    text += f"▫️ Win Rate: {accuracy}%\n\n"
    text += f"🏃 *Performance*\n"
    text += f"▫️ Total Runs: {stats.get('runs', 0)}\n"
    text += f"▫️ Wickets Taken: {stats.get('wickets', 0)}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def leaderboard_callback(update: Update, context: CallbackContext) -> None:
    """Handle leaderboard button callback"""
    query = update.callback_query
    
    top_players = user_collection.find({}, {"_id": 0, "user_id": 1, "first_name": 1, "stats": 1}) \
                                .sort([("stats.wins", -1), ("stats.runs", -1)]) \
                                .limit(10)
    
    text = "🏆 *Leaderboard:*\n\n"
    player_list = list(top_players)  # Convert cursor to list to prevent cursor timeout
    
    for idx, player in enumerate(player_list, 1):
        stats = player.get("stats", {})
        text += f"{idx}. {player.get('first_name', 'Unknown')} - Wins: {stats.get('wins', 0)}, Runs: {stats.get('runs', 0)}\n"
    

async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Handle the /leaderboard command"""
    top_players = user_collection.find({}, {"_id": 0, "user_id": 1, "first_name": 1, "stats": 1}) \
                                .sort([("stats.wins", -1), ("stats.runs", -1)]) \
                                .limit(25)
    
    text = "🏆 *Leaderboard:*\n\n"
    player_list = list(top_players)  # Convert cursor to list to prevent cursor timeout
    
    for idx, player in enumerate(player_list, 1):
        stats = player.get("stats", {})
        text += f"{idx}. {player.get('first_name', 'Unknown')} - Wins: {stats.get('wins', 0)}, Runs: {stats.get('runs', 0)}\n"
    await update.message.reply_text(text, parse_mode="Markdown")    
    
def setup_jobs(application):
    job_queue = application.job_queue

    # Clean up inactive games every 5 minutes
    job_queue.run_repeating(
        callback=cleanup_inactive_games,
        interval=300,
        first=10
    )

async def cleanup_inactive_games(context: CallbackContext):
    current_time = datetime.utcnow()
    
    # Clean up in-memory games
    games_to_remove = []
    for game_id, game in list(cricket_games.items()):
        last_move = game.get("last_move", datetime.utcnow() - timedelta(minutes=11))
        if (current_time - last_move).total_seconds() > 600:  # 10 minutes of inactivity
            games_to_remove.append(game_id)
            try:
                db['cricket_games'].update_one(
                    {"game_id": game_id},
                    {"$set": {"active": False}}
                )
            except:
                pass
    
    for game_id in games_to_remove:
        cricket_games.pop(game_id, None)
    
    # Clean up MongoDB games
    db['cricket_games'].update_many(
        {"last_move": {"$lte": current_time - timedelta(minutes=10)}},
        {"$set": {"active": False}}
    )
    
async def show_achievements_by_category(update: Update, context: CallbackContext, category_index: int = 0) -> None:
    # Check if the user is the initiator
    if 'achievements_initiator' not in context.user_data:
        await update.message.reply_text("You didn't start the achievements interface.")
        return

    initiator_id = context.user_data['achievements_initiator']
    if update.effective_user.id != initiator_id:
        await update.message.reply_text("You are not authorized to view these achievements.")
        return

    # Rest of your existing code for showing achievements
    user = update.effective_user
    user_id = str(user.id)
    
    user_achievements = achievements_collection.find_one({"user_id": user_id})
    earned_ids = user_achievements.get("achievements", []) if user_achievements else []
    
    if category_index < 0 or category_index >= len(ACHIEVEMENT_CATEGORIES):
        category_index = 0
    
    current_category = ACHIEVEMENT_CATEGORIES[category_index]
    category_achievements = ACHIEVEMENTS.get(current_category, [])
    earned_in_category = [a for a in category_achievements if a["id"] in earned_ids]
    
    text = f"🏆 *{current_category} Achievements*\n\n"
    if not earned_in_category:
        text += "No achievements in this category yet!"
    else:
        for achievement in earned_in_category:
            text += f"*{achievement['name']}*\n"
            text += f"_{achievement['description']}_\n\n"
    
    keyboard = []
    prev_button = None
    next_button = None
    
    if category_index > 0:
        prev_button = InlineKeyboardButton("⬅️", callback_data=f"category_{category_index-1}_{user_id}")
    if category_index < len(ACHIEVEMENT_CATEGORIES) - 1:
        next_button = InlineKeyboardButton("➡️", callback_data=f"category_{category_index+1}_{user_id}")
    
    middle_button = InlineKeyboardButton(current_category, callback_data="noop")
    nav_row = []
    if prev_button:
        nav_row.append(prev_button)
    nav_row.append(middle_button)
    if next_button:
        nav_row.append(next_button)
    keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data=f"close_achievements_{user_id}")])
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error updating message: {e}")
    else:
        try:
            await update.message.reply_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")

async def category_navigation_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    user_id = str(update.effective_user.id)
    
    # Check if the user is the initiator
    if 'achievements_initiator' not in context.user_data:
        await query.answer("You didn't start the achievements interface.")
        return

    initiator_id = context.user_data['achievements_initiator']
    if update.effective_user.id != initiator_id:
        await query.answer("You are not authorized to use these buttons.", show_alert=True)
        return
    
    # Rest of your existing code for handling category navigation
    if data.startswith("category_"):
        try:
            parts = data.split("_")
            category_index = int(parts[1])
            await show_achievements_by_category(update, context, category_index)
        except (ValueError, IndexError):
            await query.answer("Invalid category")
    
    elif data.startswith("close_achievements"):
        await query.answer("Closed achievements")
        await query.message.delete()

async def achievements_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    context.user_data['achievements_initiator'] = user_id  # Store the initiator's user ID
    await show_achievements_by_category(update, context, 0)

async def check_achievements(user_id, context=None):
    user_id_str = str(user_id)
    
    user_data = user_collection.find_one({"user_id": user_id_str}, {"stats": 1})
    if not user_data or "stats" not in user_data:
        return []
    
    stats = user_data["stats"]
    
    user_achievements = achievements_collection.find_one({"user_id": user_id_str})
    if not user_achievements:
        user_achievements = {"user_id": user_id_str, "achievements": []}
        achievements_collection.insert_one(user_achievements)
    
    earned_ids = set(user_achievements.get("achievements", []))
    newly_earned = []
    
    matches_played = stats.get("wins", 0) + stats.get("losses", 0)
    accuracy = round((stats.get("wins", 0) / matches_played) * 100) if matches_played > 0 else 0
    
    for category, achievements in ACHIEVEMENTS.items():
        for achievement in achievements:
            if achievement["id"] in earned_ids:
                continue  # Skip if already earned
            
            req_type = achievement["requirement"]["type"]
            req_value = achievement["requirement"]["value"]
            
            # Ensure req_value is an integer
            if not isinstance(req_value, int):
                try:
                    req_value = int(req_value)
                except (ValueError, TypeError):
                    continue  # Skip if conversion fails
            
            current_value = 0
            if req_type == "runs":
                current_value = stats.get("runs", 0)
            elif req_type == "wickets":
                current_value = stats.get("wickets", 0)
            elif req_type == "wins":
                current_value = stats.get("wins", 0)
            elif req_type == "matches":
                current_value = matches_played
            elif req_type == "accuracy":
                current_value = accuracy
            elif req_type == "streak":
                current_value = stats.get("current_streak", 0)
            
            if current_value >= req_value:
                achievements_collection.update_one(
                    {"user_id": user_id_str},
                    {"$addToSet": {"achievements": achievement["id"]}}
                )
                newly_earned.append(achievement)
                if context:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🏆 *Achievement Unlocked!*\n\n*{achievement['name']}*\n{achievement['description']}",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Error sending achievement notification: {e}")
    
    return newly_earned

async def check_special_achievement(game_id: str, achievement_type: str, context: CallbackContext, player_id=None) -> None:
    game = cricket_games[game_id]
    recipients = [player_id] if player_id else [game["player1"], game["player2"]]
    
    for user_id in recipients:
        user_id_str = str(user_id)
        user_achievements = achievements_collection.find_one({"user_id": user_id_str})
        if not user_achievements:
            user_achievements = {"user_id": user_id_str, "achievements": []}
            achievements_collection.insert_one(user_achievements)
        
        earned_ids = set(user_achievements.get("achievements", []))
        
        for achievement in ACHIEVEMENTS["Special"]:
            if (achievement["id"] not in earned_ids and 
                achievement["requirement"]["value"] == achievement_type):
                achievements_collection.update_one(
                    {"user_id": user_id_str},
                    {"$addToSet": {"achievements": achievement["id"]}}
                )
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🏆 *Achievement Unlocked!*\n\n*{achievement['name']}*\n{achievement['description']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error sending special achievement notification: {e}")

async def check_streaks(user_id: int, context: CallbackContext) -> None:
    user_id_str = str(user_id)
    user_data = user_collection.find_one({"user_id": user_id_str})
    if not user_data or "stats" not in user_data:
        return
    
    current_streak = user_data["stats"].get("current_streak", 0)
    
    if current_streak > 0:
        user_achievements = achievements_collection.find_one({"user_id": user_id_str})
        if not user_achievements:
            user_achievements = {"user_id": user_id_str, "achievements": []}
            achievements_collection.insert_one(user_achievements)
        
        earned_ids = set(user_achievements.get("achievements", []))
        
        for achievement in ACHIEVEMENTS["Streaks"]:
            if (achievement["id"] not in earned_ids and 
                current_streak >= achievement["requirement"]["value"]):
                achievements_collection.update_one(
                    {"user_id": user_id_str},
                    {"$addToSet": {"achievements": achievement["id"]}}
                )
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🏆 *Achievement Unlocked!*\n\n*{achievement['name']}*\n{achievement['description']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error sending streak achievement notification: {e}")

async def tag_active_users(update: Update, context: CallbackContext) -> None:
    if not await check_user_started_bot(update, context):
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if user is an admin in the chat
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['creator', 'administrator']:
        await update.message.reply_text(
            "Only group administrators can use this command."
        )
        return
    
    # Send a typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Get current time in UTC
    now_utc = datetime.utcnow()
    
    # Convert to IST for display
    ist_timezone = pytz.timezone('Asia/Kolkata')
    now_ist = pytz.utc.localize(now_utc).astimezone(ist_timezone)
    
    # Calculate 5 minutes ago in UTC for database query
    five_minutes_ago_utc = now_utc - timedelta(minutes=5)
    
    logger.info(f"Current IST time: {now_ist.strftime('%H:%M:%S')}, Checking activity since: {five_minutes_ago_utc}")
    
    # Find users who were active in the last 5 minutes
    try:
        active_users = list(user_collection.find({
            "$or": [
                {"last_active": {"$gte": five_minutes_ago_utc}},
                {"last_seen": {"$gte": five_minutes_ago_utc}}
            ]
        }))
        
        logger.info(f"Found {len(active_users)} active users in the last 5 minutes")
    except Exception as e:
        logger.error(f"Error querying database: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while retrieving active users.",
        )
        return
    
    tagged_users = []
    for user_doc in active_users:
        user_id = user_doc.get("user_id")
        if not user_id:
            continue
            
        try:
            # Get user's first name or fallback to user ID
            user_name = user_doc.get("first_name", str(user_id))
            last_active_utc = user_doc.get("last_active") or user_doc.get("last_seen")
            
            # Convert UTC time to IST
            if isinstance(last_active_utc, datetime):
                # Localize the datetime object to UTC then convert to IST
                last_active_ist = pytz.utc.localize(last_active_utc).astimezone(ist_timezone)
                time_str = last_active_ist.strftime("%H:%M:%S")
            else:
                # If it's not a datetime object, just use it as is
                time_str = "unknown"
                
            tagged_users.append(f"[{user_name}](tg://user?id={user_id}) - active at {time_str} IST")
        except Exception as e:
            logger.error(f"Error processing user {user_id}: {e}")
    
    if not tagged_users:
        await context.bot.send_message(
            chat_id=chat_id,
            text="No active users found in the last 5 minutes.",
            parse_mode="Markdown"
        )
        return
    
    # Limit the number of users tagged to prevent message too long errors
    max_users_per_message = 50
    
    for i in range(0, len(tagged_users), max_users_per_message):
        chunk = tagged_users[i:i + max_users_per_message]
        message = f"Active users in the last 5 minutes ({len(chunk)}):\n" + "\n".join(chunk)
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending tagged users message: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="An error occurred while tagging users.",
            )

async def get_first_name(context, user_id):
    try:
        return (await get_user_name_cached(user_id, context))
    except:
        return "Player"

# Multiplayer Game Logic
def get_current_utc_time():
    return datetime.now(pytz.utc)

async def update_last_move(game_id: str):
    current_time = get_current_utc_time()
    try:
        multiplayer_game_collection.update_one(
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
            text=f"⚠️ {user_tag}, you need to start the bot first!\n"
                 f"Click the button below to start the bot.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return False
    return True

async def get_game_data(game_id: str) -> dict:
    game_id = str(game_id)
    if game_id in multiplayer_games:
        return multiplayer_games[game_id]
    # Try to load from DB
    game_data = multiplayer_game_collection.find_one({"game_id": game_id})
    if game_data:
        game = {k: v for k, v in game_data.items() if k != "_id"}
        multiplayer_games[game_id] = game
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

    multiplayer_games[game_id] = game
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
        multiplayer_games[game_id] = game
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
    
    multiplayer_games[game_id] = game
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
    
    multiplayer_games[game_id] = game
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
    
    multiplayer_games[game_id] = game
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
        
        multiplayer_games[game_id] = game
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
        
        multiplayer_games[game_id] = game
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
            multiplayer_games[game_id] = game
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
        
        multiplayer_games[game_id] = game
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
                    
            multiplayer_games[game_id] = game
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
            multiplayer_games[game_id] = game
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
        
        multiplayer_games[game_id] = game
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
        
        multiplayer_games[game_id] = game
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
    
    if game_id in multiplayer_games:
        del multiplayer_games[game_id]
    
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
    
    if game_id in multiplayer_games:
        del multiplayer_games[game_id]
    
    game_collection.delete_one({"game_id": game_id})
    
    await query.answer("Game cancelled!")

def get_cricket_handlers():
    return [
        CommandHandler("multiplayer", multiplayer),
        CommandHandler("chatcricket", chat_cricket),
        CommandHandler("stats", stats),
        CommandHandler("leaderboard", leaderboard),
        CommandHandler("history", game_history),
        CommandHandler("chat", chat_command),
        CommandHandler("tagactive", tag_active_users),
        CommandHandler("achievements", achievements_command),
        CallbackQueryHandler(handle_join_button, pattern=r"^join_"),
        CallbackQueryHandler(handle_remove_button, pattern=r"^remove_"),
        CallbackQueryHandler(handle_play_button, pattern=r"^play_"),
        CallbackQueryHandler(handle_cancel_button, pattern=r"^cancel_"),
        CallbackQueryHandler(toss_button, pattern="^toss_"),
        CallbackQueryHandler(choose_button, pattern="^choose_"),
        CallbackQueryHandler(category_navigation_callback, pattern=r"^category_"),
        CallbackQueryHandler(category_navigation_callback, pattern=r"^close_achievements$")
    ]
