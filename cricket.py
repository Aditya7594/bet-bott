from pymongo import MongoClient
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
from datetime import datetime, timedelta
import logging
from functools import wraps
import string
import asyncio

# MongoDB connection
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
user_collection = db["users"]
cricket_collection = db["cricket_games"]

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Global dictionary to store active games in memory
cricket_games = {}

# Fetch user data from database
def get_user_by_id(user_id):
    """Fetch user data from database."""
    return db['users'].find_one({"user_id": user_id})

def save_user(user_data):
    """Save or update user data in database."""
    db['users'].update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def generate_game_code():
    """Generate a unique game code."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not cricket_collection.find_one({"game_code": code}):
            return code

async def chat_cricket(update: Update, context: CallbackContext) -> None:
    """Start a new cricket game."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats!")
        return

    user = update.effective_user
    user_id = str(user.id)
    
    # Check if user has started the bot
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Generate unique game code
    game_code = generate_game_code()
    
    # Create game data
    game_data = {
        "game_code": game_code,
        "group_chat_id": update.effective_chat.id,
        "player1": user_id,
        "player2": None,
        "spectators": [],
        "status": "waiting",
        "created_at": datetime.utcnow(),
        "last_move": datetime.utcnow(),
        "active": True,
        "score1": 0,
        "score2": 0,
        "wickets": 0,
        "over": 0,
        "ball": 0,
        "max_overs": 5,
        "max_wickets": 10,
        "innings": 1,
        "target": 0,
        "toss_winner": None,
        "batter": None,
        "bowler": None
    }
    
    try:
        # Insert game into database and memory
        cricket_collection.insert_one(game_data)
        cricket_games[game_code] = game_data
        
        # Create join and watch buttons with callbacks
        keyboard = [
            [
                InlineKeyboardButton("🎮 Join Game", callback_data=f"cricket_join_{game_code}"),
                InlineKeyboardButton("👁️ Watch Game", callback_data=f"cricket_watch_{game_code}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send game creation message with copyable code
        await update.message.reply_text(
            f"🎮 *New Cricket Game Created!*\n\n"
            f"Game Code: `{game_code}`\n"
            f"Created by: {user.first_name}\n\n"
            f"To join the game:\n"
            f"1. Click the Join Game button\n"
            f"2. Or copy and use: `/join {game_code}`\n\n"
            f"To watch the game:\n"
            f"1. Click the Watch Game button\n"
            f"2. Or copy and use: `/watch {game_code}`",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error creating cricket game: {e}")
        await update.message.reply_text("❌ An error occurred while creating the game. Please try again.")

async def handle_cricket_callback(update: Update, context: CallbackContext) -> None:
    """Handle all cricket game callbacks."""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data
    try:
        _, action, game_code = query.data.split("_")
    except ValueError:
        await query.edit_message_text("❌ Invalid callback data.")
        return
    
    # Ensure game exists in memory and database
    game = cricket_collection.find_one({"game_code": game_code})
    if not game:
        await query.edit_message_text("❌ Game not found.")
        return
    
    # Update memory cache if needed
    if game_code not in cricket_games:
        cricket_games[game_code] = game

    user_id = str(query.from_user.id)
    
    try:
        if action == "join":
            await handle_join_game(query, game_code, user_id)
        elif action == "watch":
            await handle_watch_game(query, game_code, user_id)
        elif action == "toss":
            # Get toss choice from additional data
            toss_choice = query.data.split("_")[-1] if len(query.data.split("_")) > 3 else None
            await handle_toss(query, game_code, user_id, toss_choice)
        elif action in ["bat", "bowl"]:
            await handle_choose(query, game_code, action, user_id)
        elif action == "play":
            await handle_play(query, game_code, user_id)
        elif action == "wicket":
            await handle_wicket(query, game_code, user_id)
        elif action == "end_innings":
            await handle_end_innings(query, game_code, user_id)
    except Exception as e:
        logger.error(f"Error in handle_cricket_callback: {e}")
        await query.edit_message_text("❌ An unexpected error occurred.")

async def handle_join_game(query, game_code, user_id):
    """Handle when a user joins a game."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if game["player2"] is not None:
        await query.answer("This game is already full!")
        return

    if user_id == str(game["player1"]):
        await query.answer("You cannot join your own game!")
        return

    # Update game with player2
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"player2": user_id, "last_move": datetime.utcnow()}}
    )

    # Update memory cache
    cricket_games[game_code]["player2"] = user_id
    cricket_games[game_code]["last_move"] = datetime.utcnow()

    # Prepare players information
    player1 = await query.bot.get_chat(int(game["player1"]))
    player2 = query.from_user

    # Update game message in group chat
    await query.edit_message_text(
        f"🎮 *Cricket Game Started!*\n\n"
        f"Game Code: `{game_code}`\n"
        f"Player 1: {player1.mention_html()}\n"
        f"Player 2: {player2.mention_html()}\n\n"
        f"Starting toss...",
        parse_mode="HTML"
    )

    # Delay and start toss
    await asyncio.sleep(1)
    await start_toss(query, game_code)

async def handle_watch_game(query, game_code, user_id):
    """Handle when a user watches a game."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id in game.get("spectators", []):
        await query.answer("You are already watching this game!")
        return

    # Add user to spectators
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$addToSet": {"spectators": user_id}, "$set": {"last_move": datetime.utcnow()}}
    )

    await query.answer("You are now watching the game!")
    await update_game_interface(game_code, query)

async def start_toss(query, game_code):
    """Start the toss process."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    keyboard = [
        [
            InlineKeyboardButton("Heads", callback_data=f"cricket_toss_{game_code}_heads"),
            InlineKeyboardButton("Tails", callback_data=f"cricket_toss_{game_code}_tails")
        ]
    ]

    player1 = await query.bot.get_chat(int(game["player1"]))
    player2 = await query.bot.get_chat(int(game["player2"]))

    await query.edit_message_text(
        f"🎲 *Toss Time!*\n\n"
        f"{player1.mention_html()} vs {player2.mention_html()}\n"
        f"Choose Heads or Tails:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_toss(query, game_code, user_id, toss_choice=None):
    """Handle the toss result."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    # If no toss choice, it means the first toss stage
    if not toss_choice:
        if user_id not in [game["player1"], game["player2"]]:
            await query.answer("You're not part of this game!")
            return

        keyboard = [
            [
                InlineKeyboardButton("Heads", callback_data=f"cricket_toss_{game_code}_heads"),
                InlineKeyboardButton("Tails", callback_data=f"cricket_toss_{game_code}_tails")
            ]
        ]

        await query.edit_message_text(
            f"🎲 *Toss Time!*\n"
            f"Choose Heads or Tails:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return

    # Toss logic
    result = random.choice(["heads", "tails"])
    winner_id = user_id if toss_choice == result else (game["player2"] if user_id == game["player1"] else game["player1"])
    winner = await query.bot.get_chat(int(winner_id))

    # Update game with toss winner
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"toss_winner": winner_id, "last_move": datetime.utcnow()}}
    )
    cricket_games[game_code]["toss_winner"] = winner_id

    keyboard = [
        [InlineKeyboardButton("Batting", callback_data=f"cricket_bat_{game_code}")],
        [InlineKeyboardButton("Bowling", callback_data=f"cricket_bowl_{game_code}")]
    ]

    await query.edit_message_text(
        f"🎲 *Toss Result: {result.upper()}*\n\n"
        f"{winner.mention_html()} won the toss!\n"
        f"Choose to bat or bowl:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_choose(query, game_code, choice, user_id):
    """Handle batting/bowling choice."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id != game["toss_winner"]:
        await query.answer("It's not your turn to choose!")
        return

    # Determine batter and bowler based on toss winner's choice
    if choice == "bat":
        batter = int(user_id)
        bowler = int(game["player2"] if user_id == game["player1"] else game["player1"])
    else:
        bowler = int(user_id)
        batter = int(game["player2"] if user_id == game["player1"] else game["player1"])

    # Update game with choice
    update_data = {
        "batter_choice": choice,
        "batter": batter,
        "bowler": bowler,
        "last_move": datetime.utcnow()
    }

    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": update_data}
    )
    cricket_games[game_code].update(update_data)

    # Get player mentions
    batter_mention = await query.bot.get_chat(batter)
    bowler_mention = await query.bot.get_chat(bowler)

    keyboard = [
        [InlineKeyboardButton("Start Game", callback_data=f"cricket_play_{game_code}")]
    ]

    await query.edit_message_text(
        f"🎮 *Game Setup Complete!*\n\n"
        f"{batter_mention.mention_html()} is batting\n"
        f"{bowler_mention.mention_html()} is bowling\n\n"
        f"Click Start Game to begin:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_play(query, game_code, user_id):
    """Handle a ball being played."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id != str(game["bowler"]):
        await query.answer("It's not your turn to bowl!")
        return

    # Simulate ball outcome
    outcomes = ["0", "1", "2", "3", "4", "6", "W"]
    weights = [0.2, 0.2, 0.15, 0.1, 0.15, 0.1, 0.1]
    outcome = random.choices(outcomes, weights=weights)[0]

    # Update game state
    update_data = {"last_move": datetime.utcnow()}
    
    if outcome == "W":
        update_data["wickets"] = game["wickets"] + 1
        if update_data["wickets"] >= game["max_wickets"]:
            await handle_end_innings(query, game_code, user_id)
            return
    else:
        runs = int(outcome)
        if game["innings"] == 1:
            update_data["score1"] = game["score1"] + runs
        else:
            update_data["score2"] = game["score2"] + runs
            if update_data["score2"] > game["score1"]:
                await declare_winner(query, game_code)
                return

    update_data["ball"] = game["ball"] + 1
    if update_data["ball"] >= 6:
        update_data["over"] = game["over"] + 1
        update_data["ball"] = 0
        if update_data["over"] >= game["max_overs"]:
            await handle_end_innings(query, game_code, user_id)
            return

    # Update both database and memory cache
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": update_data}
    )
    cricket_games[game_code].update(update_data)

    keyboard = [
        [InlineKeyboardButton("Next Ball", callback_data=f"cricket_play_{game_code}")]
    ]

    await query.edit_message_text(
        f"🎮 *Cricket Game in Progress*\n\n"
        f"Over: {update_data['over']}.{update_data['ball']}\n"
        f"Score: {update_data.get('score1', game['score1']) if game['innings'] == 1 else update_data.get('score2', game['score2'])}/{update_data.get('wickets', game['wickets'])}\n"
        f"Target: {game['target'] if game['innings'] == 2 else 'N/A'}\n\n"
        f"Last ball: {outcome}\n"
        f"{(await query.bot.get_chat(game['batter'])).mention_html()} is batting\n"
        f"{(await query.bot.get_chat(game['bowler'])).mention_html()} is bowling",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_wicket(query, game_code, user_id):
    game = cricket_games.get(game_code)
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id != str(game["bowler"]):
        await query.answer("It's not your turn to bowl!")
        return

    game["wickets"] += 1
    if game["wickets"] >= game["max_wickets"]:
        await handle_end_innings(query, game_code, user_id)
        return

    game["last_move"] = datetime.utcnow()
    cricket_games[game_code] = game
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"wickets": game["wickets"], "last_move": datetime.utcnow()}}
    )

    keyboard = [
        [InlineKeyboardButton("Next Ball", callback_data=f"cricket_play_{game_code}")]
    ]

    await query.edit_message_text(
        f"🎮 *Cricket Game in Progress*\n\n"
        f"Over: {game['over']}.{game['ball']}\n"
        f"Score: {game['score1'] if game['innings'] == 1 else game['score2']}/{game['wickets']}\n"
        f"Target: {game['target'] if game['innings'] == 2 else 'N/A'}\n\n"
        f"Last ball: W\n"
        f"{(await query.bot.get_chat(game['batter'])).mention_html()} is batting\n"
        f"{(await query.bot.get_chat(game['bowler'])).mention_html()} is bowling",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_end_innings(query, game_code, user_id):
    """Handle end of innings."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if game["innings"] == 1:
        # Update game for second innings
        update_data = {
            "innings": 2,
            "target": game["score1"] + 1,
            "score2": 0,
            "wickets": 0,
            "over": 0,
            "ball": 0,
            "batter": game["bowler"],
            "bowler": game["batter"],
            "last_move": datetime.utcnow()
        }

        # Update both database and memory cache
        cricket_collection.update_one(
            {"game_code": game_code},
            {"$set": update_data}
        )
        cricket_games[game_code].update(update_data)

        keyboard = [
            [InlineKeyboardButton("Start Second Innings", callback_data=f"cricket_play_{game_code}")]
        ]

        await query.edit_message_text(
            f"🎮 *First Innings Complete!*\n\n"
            f"Score: {game['score1']}/{game['max_wickets']}\n"
            f"Target: {update_data['target']}\n\n"
            f"{(await query.bot.get_chat(update_data['batter'])).mention_html()} is batting\n"
            f"{(await query.bot.get_chat(update_data['bowler'])).mention_html()} is bowling",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        await declare_winner(query, game_code)

async def declare_winner(query, game_code):
    """Declare the winner of the game."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game:
        return

    # Update game status
    update_data = {"active": False, "last_move": datetime.utcnow()}
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": update_data}
    )
    cricket_games[game_code].update(update_data)

    # Determine winner
    if game["score2"] > game["score1"]:
        winner = await query.bot.get_chat(game["batter"])
        margin = game["score2"] - game["score1"]
        result = f"{winner.mention_html()} won by {game['max_wickets'] - game['wickets']} wickets!"
    elif game["score2"] < game["score1"]:
        winner = await query.bot.get_chat(game["bowler"])
        margin = game["score1"] - game["score2"]
        result = f"{winner.mention_html()} won by {margin} runs!"
    else:
        result = "It's a tie!"

    await query.edit_message_text(
        f"🎮 *Game Over!* 🎮\n\n"
        f"First Innings: {game['score1']}/{game['max_wickets']}\n"
        f"Second Innings: {game['score2']}/{game['wickets']}\n\n"
        f"{result}",
        parse_mode="HTML"
    )

async def handle_cricket_message(update: Update, context: CallbackContext) -> None:
    """Handle messages during an active Cricket game."""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    # Find active game in this chat
    game = cricket_collection.find_one({
        "active": True,
        "$or": [
            {"player1": user_id},
            {"player2": user_id}
        ]
    })
    
    if not game:
        return
        
    # Check for game timeout
    if (datetime.utcnow() - game["last_move"]) > timedelta(minutes=5):
        await handle_timeout(update, game)
        return
        
    # Delete the message and warn the user
    try:
        await update.message.delete()
        warning_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Please use the game buttons to play! Messages are not allowed during active matches.",
            delete_after=3
        )
    except Exception as e:
        logger.error(f"Error handling cricket message: {e}")

async def handle_timeout(update, game):
    """Handle game timeout."""
    try:
        # Update game status
        cricket_collection.update_one(
            {"game_code": game["game_code"]},
            {"$set": {"active": False, "status": "timeout"}}
        )
        
        # Remove from memory cache
        if game["game_code"] in cricket_games:
            del cricket_games[game["game_code"]]
        
        # Send timeout message
        await update.message.reply_text(
            "⏰ Game timed out due to inactivity. Use /chatcricket to start a new game."
        )
    except Exception as e:
        logger.error(f"Error handling game timeout: {e}")

def get_cricket_handlers():
    """Get all cricket game handlers."""
    return [
        CommandHandler("chatcricket", chat_cricket),
        CallbackQueryHandler(handle_cricket_callback, pattern=r"^cricket_(join|watch|toss|bat|bowl|play|wicket|end_innings)_[0-9A-Z]+"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cricket_message)
    ]

# Add error handling and logging
async def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')
