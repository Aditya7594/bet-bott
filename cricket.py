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

BOT_TOKEN = "8104505314:AAHeleqAEIJPuGmxPw80c_BsCU6gsRKhYlo"

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
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("Start Bot", url=f"https://t.me/{bot_username}?start=start")]]
        await update.message.reply_text(
            "⚠️ You need to start the bot first to create a match!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
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
        "bowler": None,
        "message_id": {},
        "current_players": {},
        "batter_choice": None,
        "bowler_choice": None,
        "match_details": []
    }
    
    try:
        # Insert game into database and memory
        cricket_collection.insert_one(game_data)
        cricket_games[game_code] = game_data
        
        # Create join and watch buttons with URLs
        bot_username = (await context.bot.get_me()).username
        join_button = InlineKeyboardButton("Join Game", url=f"https://t.me/{bot_username}?start=join_{game_code}")
        watch_button = InlineKeyboardButton("Watch Game", url=f"https://t.me/{bot_username}?start=watch_{game_code}")
        keyboard = InlineKeyboardMarkup([[join_button], [watch_button]])
        
        # Send game creation message with copyable code
        sent_message = await update.message.reply_text(
            f"🎮 *Game Started!*\nCode: `{game_code}`\n\n"
            f"To join, click the button or send /join {game_code}\n"
            f"To watch, click Watch Game or send /watch {game_code}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Pin the message
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=sent_message.message_id
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
        action, game_code = query.data.split("_")
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
        if action == "toss":
            # Get toss choice from additional data
            toss_choice = query.data.split("_")[-1] if len(query.data.split("_")) > 2 else None
            await handle_toss(query, game_code, user_id, toss_choice)
        elif action == "choose":
            choice = query.data.split("_")[-1]
            await handle_choose(query, game_code, choice, user_id)
        elif action == "play":
            number = int(query.data.split("_")[-1])
            await handle_play(query, game_code, user_id, number)
        elif action == "cancel":
            await handle_cancel(query, game_code, user_id)
    except Exception as e:
        logger.error(f"Error in handle_cricket_callback: {e}")
        await query.edit_message_text("❌ An unexpected error occurred.")

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
                InlineKeyboardButton("Heads", callback_data=f"toss_{game_code}_heads"),
                InlineKeyboardButton("Tails", callback_data=f"toss_{game_code}_tails")
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
        [InlineKeyboardButton("🏏 Bat", callback_data=f"choose_{game_code}_bat")],
        [InlineKeyboardButton("🎯 Bowl", callback_data=f"choose_{game_code}_bowl")]
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
        "current_players": {"batter": batter, "bowler": bowler},
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

    # Create number buttons for batter
    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])

    await query.edit_message_text(
        f"🎮 *Game Setup Complete!*\n\n"
        f"{batter_mention.mention_html()} is batting\n"
        f"{bowler_mention.mention_html()} is bowling\n\n"
        f"⚡ {batter_mention.first_name}, choose a number (1-6):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_play(query, game_code, user_id, number):
    """Handle a ball being played."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id == str(game["current_players"]["batter"]) and game["batter_choice"] is None:
        # Batter's turn
        game["batter_choice"] = number
        await query.answer(f"Your choice: {number}")
        
        # Update interface for batter
        batter_name = (await query.bot.get_chat(game["batter"])).first_name
        bowler_name = (await query.bot.get_chat(game["bowler"])).first_name
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
        
        text += f"\n\nYou chose: {number}\n\n⚡ {bowler_name}, choose a number (1-6):"
        
        # Create keyboard for bowler
        keyboard = []
        row = []
        for i in range(1, 7):
            row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    elif user_id == str(game["current_players"]["bowler"]) and game["bowler_choice"] is None:
        # Bowler's turn
        game["bowler_choice"] = number
        await query.answer(f"Your choice: {number}")
        
        # Process the result
        batter_choice = game["batter_choice"]
        bowler_choice = number
        
        # Reset choices for next ball
        game["batter_choice"] = None
        game["bowler_choice"] = None
        
        # Process ball result
        if batter_choice == bowler_choice:
            # Wicket
            game["wickets"] += 1
            game["match_details"].append((game["over"], game["ball"], 0, True))
            result_text = f"🎯 Ball Result: WICKET!\nBatter: {batter_choice} | Bowler: {bowler_choice}"
            
            # Update ball count
            game["ball"] += 1
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0
                
            # Check for innings end
            if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
                await handle_end_innings(query, game_code, user_id)
                return
                
        else:
            # Runs
            runs = batter_choice
            result_text = f"🎯 Ball Result: {runs} RUNS!\nBatter: {batter_choice} | Bowler: {bowler_choice}"
            
            if game["innings"] == 1:
                game["score1"] += runs
            else:
                game["score2"] += runs
                
            game["match_details"].append((game["over"], game["ball"], runs, False))
            
            # Update ball count
            game["ball"] += 1
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0
                
            # Check for innings end or target reached
            if game["innings"] == 2 and game["score2"] >= game["target"]:
                await declare_winner(query, game_code)
                return
            elif game["over"] >= game["max_overs"]:
                await handle_end_innings(query, game_code, user_id)
                return
        
        # Update game state
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
        cricket_games[game_code].update({
            "score1": game["score1"],
            "score2": game["score2"],
            "wickets": game["wickets"],
            "over": game["over"],
            "ball": game["ball"]
        })
        
        # Update interface
        batter_name = (await query.bot.get_chat(game["batter"])).first_name
        bowler_name = (await query.bot.get_chat(game["bowler"])).first_name
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
        
        text += f"\n\n{result_text}\n\n⚡ {batter_name}, choose a number (1-6):"
        
        # Create keyboard for batter
        keyboard = []
        row = []
        for i in range(1, 7):
            row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        await query.answer("Not your turn!")

async def handle_cancel(query, game_code, user_id):
    """Handle game cancellation."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    if user_id not in [game["player1"], game["player2"]]:
        await query.answer("You're not part of this game!")
        return

    # Update game status
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {"active": False, "status": "cancelled", "last_move": datetime.utcnow()}}
    )
    
    # Remove from memory cache
    if game_code in cricket_games:
        del cricket_games[game_code]
    
    # Send cancellation message
    await query.edit_message_text(
        "❌ Game cancelled. Use /chatcricket to start a new game."
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
            "current_players": {
                "batter": game["bowler"],
                "bowler": game["batter"]
            },
            "last_move": datetime.utcnow()
        }

        # Update both database and memory cache
        cricket_collection.update_one(
            {"game_code": game_code},
            {"$set": update_data}
        )
        cricket_games[game_code].update(update_data)

        # Build innings break message
        batter_name = (await query.bot.get_chat(update_data["batter"])).first_name
        bowler_name = (await query.bot.get_chat(update_data["bowler"])).first_name
        spectator_count = len(game["spectators"])
        spectator_text = f"👁️ {spectator_count}" if spectator_count > 0 else ""
        
        text = (
            f"🔥 *INNINGS BREAK* 🔥\n\n"
            f"First innings score: {game['score1']}\n"
            f"Target: {update_data['target']} runs\n\n"
            f"⏳ Over: {update_data['over']}.{update_data['ball']}  {spectator_text}\n"
            f"🔸 Now batting: {batter_name}\n"
            f"🔹 Now bowling: {bowler_name}\n\n"
            f"⚡ {batter_name}, choose a number (1-6):"
        )
        
        # Create keyboard for batter
        keyboard = []
        row = []
        for i in range(1, 7):
            row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])
        
        await query.edit_message_text(
            text=text,
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

    # Build result message
    result_message = (
        f"🏆 *GAME OVER!*\n\n"
        f"📜 *Match Summary:*\n"
        f"🧑 {(await query.bot.get_chat(game['player1'])).first_name}: {game['score1']} runs\n"
        f"🧑 {(await query.bot.get_chat(game['player2'])).first_name}: {game['score2']} runs\n\n"
        f"{result}"
    )

    # Send result to group chat
    try:
        await query.bot.send_message(
            chat_id=game["group_chat_id"],
            text=result_message,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error sending result to group chat: {e}")

    # Send result to players and spectators
    participants = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in participants:
        try:
            await query.bot.send_message(
                chat_id=player_id,
                text=result_message,
                parse_mode="HTML"
            )
            
            # Try to unpin the game message
            try:
                await query.bot.unpin_chat_message(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id)
                )
            except Exception as e:
                logger.error(f"Error unpinning message for {player_id}: {e}")
                
        except Exception as e:
            logger.error(f"Error sending result to {player_id}: {e}")

    # Remove from memory cache
    if game_code in cricket_games:
        del cricket_games[game_code]

async def handle_cricket_message(update: Update, context: CallbackContext) -> None:
    """Handle messages during an active Cricket game."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Find active game in this chat
    game = cricket_collection.find_one({
        "active": True,
        "$or": [
            {"player1": str(user_id)},
            {"player2": str(user_id)}
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

    try:
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

        # Send game message to both players in their DMs
        game_message = (
            f"🎮 *Cricket Game Started!*\n\n"
            f"Game Code: `{game_code}`\n"
            f"Player 1: {player1.mention_html()}\n"
            f"Player 2: {player2.mention_html()}\n\n"
            f"Starting toss..."
        )

        # Send to player 1
        await query.bot.send_message(
            chat_id=int(game["player1"]),
            text=game_message,
            parse_mode="HTML"
        )

        # Send to player 2
        await query.bot.send_message(
            chat_id=int(user_id),
            text=game_message,
            parse_mode="HTML"
        )

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
        await handle_toss(query, game_code, user_id)

    except Exception as e:
        logger.error(f"Error in handle_join_game: {e}")
        await query.edit_message_text("❌ An error occurred while joining the game. Please try again.")

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

async def handle_wicket(query, game_code, user_id):
    """Handle when a wicket is taken."""
    game = cricket_collection.find_one({"game_code": game_code})
    if not game or not game.get("active"):
        await query.edit_message_text("❌ This game is no longer active or doesn't exist.")
        return

    # Update ball count
    game["ball"] += 1
    if game["ball"] == 6:
        game["over"] += 1
        game["ball"] = 0

    # Check if we need to end the innings
    if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
        await handle_end_innings(query, game_code, user_id)
        return
    
    # Continue the current innings
    batter_name = (await query.bot.get_chat(game["batter"])).first_name
    bowler_name = (await query.bot.get_chat(game["bowler"])).first_name
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
    
    text += "\n\n⚡ Next ball. Batter, choose a number (1-6):"
    
    # Create keyboard for batter
    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])

    # Update game state
    cricket_collection.update_one(
        {"game_code": game_code},
        {"$set": {
            "ball": game["ball"],
            "over": game["over"],
            "last_move": datetime.utcnow()
        }}
    )
    cricket_games[game_code].update({
        "ball": game["ball"],
        "over": game["over"]
    })

    # Update interface for all participants
    recipients = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in recipients:
        try:
            await query.bot.edit_message_text(
                chat_id=player_id,
                message_id=game["message_id"].get(player_id),
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard) if player_id not in game["spectators"] else None,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error updating interface for {player_id}: {e}")

def get_cricket_handlers():
    """Get all cricket game handlers."""
    return [
        CommandHandler("chatcricket", chat_cricket),
        CallbackQueryHandler(handle_cricket_callback, pattern=r"^(toss|choose|play|cancel)_[0-9A-Z]+"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cricket_message)
    ]

# Add error handling and logging
async def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("chatcricket", chat_cricket))
    application.add_handler(CommandHandler("join", join_cricket))
    application.add_handler(CommandHandler("watch", watch_cricket))

    # Add regex handlers for deep links
    application.add_handler(MessageHandler(
        filters.Regex(r"^/start ([0-9A-Z]{6})$"),
        lambda update, context: join_cricket(update, context)
    ))
    application.add_handler(MessageHandler(
        filters.Regex(r"^/start watch_([0-9A-Z]{6})$"),
        lambda update, context: watch_cricket(update, context)
    ))
    
    # Add callback handlers
    application.add_handler(CallbackQueryHandler(handle_cricket_callback, pattern=r"^(toss|choose|play|cancel)_[0-9A-Z]+"))

    # Add message forwarding handler
    application.add_handler(MessageHandler(
        filters.TEXT | filters.Sticker.ALL,
        chat_message
    ))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
