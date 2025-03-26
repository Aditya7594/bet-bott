from pymongo import MongoClient
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
from datetime import datetime, timedelta
import logging
from functools import wraps
import string

# MongoDB connection
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
user_collection = db["users"]
cricket_collection = db["cricket_games"]

cricket_games = {}

# Fetch user data from database
def get_user_by_id(user_id):
    return db['users'].find_one({"user_id": user_id})

def save_user(user_data):
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
        "player1": user_id,
        "player2": None,
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
        "target": 0
    }
    
    try:
        # Insert game into database
        cricket_collection.insert_one(game_data)
        
        # Create join and watch buttons with URLs
        keyboard = [
            [
                InlineKeyboardButton("🎮 Join Game", url=f"https://t.me/{context.bot.username}?start=join_{game_code}"),
                InlineKeyboardButton("👁️ Watch Game", url=f"https://t.me/{context.bot.username}?start=watch_{game_code}")
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
        logging.error(f"Error creating cricket game: {e}")
        await update.message.reply_text("❌ An error occurred while creating the game. Please try again.")

async def handle_cricket_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = update.effective_user
    user_id = str(user.id)
    await query.answer()

    try:
        action, subaction, game_code = query.data.split("_")
        
        if subaction == "join":
            await handle_join_game(query, game_code, user_id)
        elif subaction == "watch":
            await handle_watch_game(query, game_code, user_id)
        elif subaction == "toss":
            await handle_toss(query, game_code, user_id)
        elif subaction == "choose":
            await handle_choose(query, game_code, user_id)
        elif subaction == "play":
            await handle_play(query, game_code, user_id)
        elif subaction == "wicket":
            await handle_wicket(query, game_code, user_id)
        elif subaction == "end":
            await handle_end_innings(query, game_code, user_id)
    except Exception as e:
        print(f"Error handling callback: {e}")
        await query.edit_message_text("❌ An error occurred while processing your action.")

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

    await query.edit_message_text(
        f"🎮 *Cricket Game Started!*\n\n"
        f"Game Code: `{game_code}`\n"
        f"Player 1: {(await query.bot.get_chat(game['player1'])).mention_html()}\n"
        f"Player 2: {query.from_user.mention_html()}\n\n"
        f"Starting toss...",
        parse_mode="HTML"
    )

    # Start toss after a short delay
    await asyncio.sleep(2)
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
    game = cricket_games.get(game_code)
    if not game:
        return

    keyboard = [
        [InlineKeyboardButton("Heads", callback_data=f"cricket_toss_{game_code}_heads")],
        [InlineKeyboardButton("Tails", callback_data=f"cricket_toss_{game_code}_tails")]
    ]

    await query.edit_message_text(
        f"🎲 *Toss Time!*\n\n"
        f"{(await query.bot.get_chat(game['player1'])).mention_html()} vs {query.from_user.mention_html()}\n"
        f"Choose Heads or Tails:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_toss(query, game_code, user_id):
    game = cricket_games.get(game_code)
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id not in [str(game["player1"]), str(game["player2"])]:
        await query.answer("You're not part of this game!")
        return

    choice = query.data.split("_")[-1]
    result = random.choice(["heads", "tails"])
    
    if choice == result:
        winner_id = user_id
        winner = query.from_user
    else:
        winner_id = str(game["player2"]) if user_id == str(game["player1"]) else str(game["player1"])
        winner = await query.bot.get_chat(int(winner_id))

    game["toss_winner"] = winner_id
    game["last_move"] = datetime.utcnow()
    cricket_games[game_code] = game
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"toss_winner": winner_id, "last_move": datetime.utcnow()}}
    )

    keyboard = [
        [InlineKeyboardButton("Batting", callback_data=f"cricket_choose_{game_code}_bat")],
        [InlineKeyboardButton("Bowling", callback_data=f"cricket_choose_{game_code}_bowl")]
    ]

    await query.edit_message_text(
        f"🎲 *Toss Result: {result.upper()}*\n\n"
        f"{winner.mention_html()} won the toss!\n"
        f"Choose to bat or bowl:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_choose(query, game_code, user_id):
    game = cricket_games.get(game_code)
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id != str(game["toss_winner"]):
        await query.answer("It's not your turn to choose!")
        return

    choice = query.data.split("_")[-1]
    game["batter_choice"] = choice
    game["last_move"] = datetime.utcnow()
    cricket_games[game_code] = game
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"batter_choice": choice, "last_move": datetime.utcnow()}}
    )

    if choice == "bat":
        game["batter"] = int(user_id)
        game["bowler"] = game["player2"] if user_id == str(game["player1"]) else game["player1"]
    else:
        game["bowler"] = int(user_id)
        game["batter"] = game["player2"] if user_id == str(game["player1"]) else game["player1"]

    keyboard = [
        [InlineKeyboardButton("Start Over", callback_data=f"cricket_play_{game_code}")]
    ]

    await query.edit_message_text(
        f"🎮 *Game Setup Complete!*\n\n"
        f"{(await query.bot.get_chat(game['batter'])).mention_html()} is batting\n"
        f"{(await query.bot.get_chat(game['bowler'])).mention_html()} is bowling\n\n"
        f"Click Start Over to begin:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_play(query, game_code, user_id):
    game = cricket_games.get(game_code)
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

    if outcome == "W":
        game["wickets"] += 1
        if game["wickets"] >= game["max_wickets"]:
            await handle_end_innings(query, game_code)
            return
    else:
        if game["innings"] == 1:
            game["score1"] += int(outcome)
        else:
            game["score2"] += int(outcome)
            if game["score2"] > game["score1"]:
                await declare_winner(game_code, query)
                return

    game["ball"] += 1
    if game["ball"] >= 6:
        game["over"] += 1
        game["ball"] = 0
        if game["over"] >= game["max_overs"]:
            await handle_end_innings(query, game_code)
            return

    game["last_move"] = datetime.utcnow()
    cricket_games[game_code] = game
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {
            "score1": game["score1"],
            "score2": game["score2"],
            "wickets": game["wickets"],
            "over": game["over"],
            "ball": game["ball"],
            "last_move": datetime.utcnow()
        }}
    )

    keyboard = [
        [InlineKeyboardButton("Next Ball", callback_data=f"cricket_play_{game_code}")]
    ]

    await query.edit_message_text(
        f"🎮 *Cricket Game in Progress*\n\n"
        f"Over: {game['over']}.{game['ball']}\n"
        f"Score: {game['score1'] if game['innings'] == 1 else game['score2']}/{game['wickets']}\n"
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
        await handle_end_innings(query, game_code)
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

async def handle_end_innings(query, game_code):
    game = cricket_games.get(game_code)
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if game["innings"] == 1:
        game["innings"] = 2
        game["target"] = game["score1"] + 1
        game["score2"] = 0
        game["wickets"] = 0
        game["over"] = 0
        game["ball"] = 0
        game["batter"], game["bowler"] = game["bowler"], game["batter"]

        game["last_move"] = datetime.utcnow()
        cricket_games[game_code] = game
        cricket_collection.update_one(
            {"game_code": game_code},
            {"$set": {
                "innings": 2,
                "target": game["target"],
                "score2": 0,
                "wickets": 0,
                "over": 0,
                "ball": 0,
                "batter": game["batter"],
                "bowler": game["bowler"],
                "last_move": datetime.utcnow()
            }}
        )

        keyboard = [
            [InlineKeyboardButton("Start Second Innings", callback_data=f"cricket_play_{game_code}")]
        ]

        await query.edit_message_text(
            f"🎮 *First Innings Complete!*\n\n"
            f"Score: {game['score1']}/{game['max_wickets']}\n"
            f"Target: {game['target']}\n\n"
            f"{(await query.bot.get_chat(game['batter'])).mention_html()} is batting\n"
            f"{(await query.bot.get_chat(game['bowler'])).mention_html()} is bowling",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        await declare_winner(game_code, query)

async def declare_winner(game_code, query):
    game = cricket_games.get(game_code)
    if not game:
        return

    game["active"] = False
    cricket_games[game_code] = game
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"active": False}}
    )

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

async def handle_cricket_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active Cricket game."""
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id not in [game["player1"], game["player2"]]:
        return
        
    # Check for game timeout
    if (datetime.utcnow() - game["last_move"]) > timedelta(minutes=5):
        await handle_timeout(update.callback_query, game)
        return
        
    # Delete the message and warn the user
    try:
        await update.message.delete()
        warning_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Please use the game buttons to play! Messages are not allowed during active matches.",
            delete_after=3
        )
    except Exception as e:
        logger.error(f"Error handling cricket message: {e}")

def get_cricket_handlers():
    """Return all cricket game handlers."""
    return [
        CommandHandler("chatcricket", chat_cricket),
        CallbackQueryHandler(handle_cricket_callback, pattern=r"^cricket_(join|watch|toss|choose|play|wicket|end)_[0-9]+")
    ]
