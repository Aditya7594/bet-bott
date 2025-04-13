from pymongo import MongoClient
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from datetime import datetime, timedelta

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

# Game state
cricket_games = {}
reminder_sent = {}
game_activity = {}

ACHIEVEMENTS = [
    # Batting achievements
    {"id": "first_run", "name": "First Run", "description": "Score your first run", "requirement": {"type": "runs", "value": 1}},
    {"id": "half_century", "name": "Half Century", "description": "Score 50 runs in total", "requirement": {"type": "runs", "value": 50}},
    {"id": "century", "name": "Century", "description": "Score 100 runs in total", "requirement": {"type": "runs", "value": 100}},
    {"id": "double_century", "name": "Double Century", "description": "Score 200 runs in total", "requirement": {"type": "runs", "value": 200}},
    {"id": "run_machine", "name": "Run Machine", "description": "Score 500 runs in total", "requirement": {"type": "runs", "value": 500}},
    {"id": "batting_legend", "name": "Batting Legend", "description": "Score 1000 runs in total", "requirement": {"type": "runs", "value": 1000}},
    
    # Wicket achievements
    {"id": "first_wicket", "name": "First Wicket", "description": "Take your first wicket", "requirement": {"type": "wickets", "value": 1}},
    {"id": "five_wickets", "name": "Five Wicket Haul", "description": "Take 5 wickets in total", "requirement": {"type": "wickets", "value": 5}},
    {"id": "ten_wickets", "name": "Ten Wicket Club", "description": "Take 10 wickets in total", "requirement": {"type": "wickets", "value": 10}},
    {"id": "wicket_master", "name": "Wicket Master", "description": "Take 25 wickets in total", "requirement": {"type": "wickets", "value": 25}},
    {"id": "bowling_legend", "name": "Bowling Legend", "description": "Take 50 wickets in total", "requirement": {"type": "wickets", "value": 50}},
    
    # Game achievements
    {"id": "first_win", "name": "First Victory", "description": "Win your first game", "requirement": {"type": "wins", "value": 1}},
    {"id": "five_wins", "name": "Winner's Circle", "description": "Win 5 games", "requirement": {"type": "wins", "value": 5}},
    {"id": "ten_wins", "name": "Champion", "description": "Win 10 games", "requirement": {"type": "wins", "value": 10}},
    {"id": "twenty_wins", "name": "Cricket Master", "description": "Win 20 games", "requirement": {"type": "wins", "value": 20}},
    {"id": "fifty_wins", "name": "Legendary Player", "description": "Win 50 games", "requirement": {"type": "wins", "value": 50}},
    
    # Match participation achievements
    {"id": "first_match", "name": "Cricket Debut", "description": "Play your first match", "requirement": {"type": "matches", "value": 1}},
    {"id": "five_matches", "name": "Regular Player", "description": "Play 5 matches", "requirement": {"type": "matches", "value": 5}},
    {"id": "ten_matches", "name": "Cricket Enthusiast", "description": "Play 10 matches", "requirement": {"type": "matches", "value": 10}},
    {"id": "fifty_matches", "name": "Cricket Veteran", "description": "Play 50 matches", "requirement": {"type": "matches", "value": 50}},
    {"id": "hundred_matches", "name": "Cricket Legend", "description": "Play 100 matches", "requirement": {"type": "matches", "value": 100}},
    
    # Accuracy/Win rate achievements
    {"id": "rising_star", "name": "Rising Star", "description": "Achieve 25% win rate", "requirement": {"type": "accuracy", "value": 25}},
    {"id": "consistent_player", "name": "Consistent Player", "description": "Achieve 40% win rate", "requirement": {"type": "accuracy", "value": 40}},
    {"id": "star_player", "name": "Star Player", "description": "Achieve 50% win rate", "requirement": {"type": "accuracy", "value": 50}},
    {"id": "elite_player", "name": "Elite Player", "description": "Achieve 60% win rate", "requirement": {"type": "accuracy", "value": 60}},
    {"id": "world_class", "name": "World Class", "description": "Achieve 75% win rate", "requirement": {"type": "accuracy", "value": 75}},
    
    # Streaks
    {"id": "winning_streak_3", "name": "Hot Streak", "description": "Win 3 games in a row", "requirement": {"type": "streak", "value": 3}},
    {"id": "winning_streak_5", "name": "Unstoppable", "description": "Win 5 games in a row", "requirement": {"type": "streak", "value": 5}},
    
    # Special achievements
    {"id": "perfect_match", "name": "Perfect Match", "description": "Win without conceding a wicket", "requirement": {"type": "special", "value": "perfect_match"}},
    {"id": "comeback_king", "name": "Comeback King", "description": "Win after being 10+ runs behind", "requirement": {"type": "special", "value": "comeback"}},
    {"id": "tied_match", "name": "Nail-Biter", "description": "Play a tied match", "requirement": {"type": "special", "value": "tie"}},
    {"id": "hat_trick", "name": "Hat-Trick", "description": "Take 3 wickets in 3 consecutive balls", "requirement": {"type": "special", "value": "hat_trick"}},
]

async def check_user_started_bot(update: Update, context: CallbackContext) -> bool:
    user = update.effective_user
    user_id = str(user.id)
    user_data = user_collection.find_one({"user_id": user_id})

    if not user_data:
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("Start Bot", url=f"https://t.me/{bot_username}?start=start")]]

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
    
    # Check if the command is used in a private chat
    if update.effective_chat.type == "private":
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ This command can only be used in group chats!"
        )
        return
    
    # Check if the user has started the bot
    if not await check_user_started_bot(update, context):
        return

    # Default values for max overs and wickets
    max_overs = 100  
    max_wickets = 1 
    
    # Check if arguments are provided and validate them
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
                text="⚠️ Invalid parameters! Format: /chatcricket [overs] [wickets]"
            )
            return

    # Get user_id from the update
    user_id = user.id  # Use update.effective_user.id to get the user's ID
    game_id = f"{chat_id}_{user_id}"  # Unique game ID per user in the group

    # Initialize the game state in a dictionary
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
    
    # Call function to update the game activity
    update_game_activity(game_id)
    
    # Prepare the game description message
    game_desc = f"🏏 *Cricket Game Started!*\n\n"
    game_desc += f"Started by: {user.first_name}\n"
    game_desc += f"Format: {max_overs} over{'s' if max_overs > 1 else ''}, {max_wickets} wicket{'s' if max_wickets > 1 else ''}\n\n"
    game_desc += f"• To join, click \"Join Game\"\n"
    game_desc += f"• To watch, click \"Watch Game\"\n"
    game_desc += f"• For the best experience, open the bot directly"
    
    # Get bot username and create an inline keyboard
    bot_username = (await context.bot.get_me()).username
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Game", callback_data=f"join_{game_id}")],
        [InlineKeyboardButton("Watch Game", callback_data=f"watch_{game_id}")],
        [InlineKeyboardButton("🎮 Open Cricket Bot", url=f"https://t.me/{bot_username}")]
    ])
    
    # Send the game start message to the group chat
    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=game_desc,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    # Pin the sent message in the group chat
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.message_id)

async def send_inactive_player_reminder(context: CallbackContext) -> None:
    current_time = datetime.utcnow()
    
    for game_id, game in list(cricket_games.items()):
        if game["player2"] is None:
            continue
            
        if game["batter"] is None or game["bowler"] is None:
            continue
            
        current_player_id = None
        if game["batter_choice"] is None:
            current_player_id = game["current_players"]["batter"]
        elif game["bowler_choice"] is None:
            current_player_id = game["current_players"]["bowler"]
        else:
            continue
        
        last_activity = game_activity.get(game_id, datetime.utcnow())
        last_reminder = game.get("last_reminder")
        
        if (current_time - last_activity).total_seconds() >= 10 and (
                last_reminder is None or (current_time - last_reminder).total_seconds() >= 10):
            
            try:
                player_name = (await context.bot.get_chat(current_player_id)).first_name
                waiting_for = "batting" if game["batter_choice"] is None else "bowling"
                
                reminder_text = (
                    f"⏰ *Reminder!* It's your turn to play cricket!\n\n"
                    f"You're currently {waiting_for}. Please make your move."
                )
                
                await context.bot.send_message(
                    chat_id=current_player_id,
                    text=reminder_text,
                    parse_mode="Markdown"
                )
                
                game["last_reminder"] = current_time
                
            except Exception as e:
                logger.error(f"Error sending play reminder: {e}")

def update_game_activity(game_id):
    game_activity[game_id] = datetime.utcnow()
    if game_id in cricket_games:
        cricket_games[game_id]["last_move"] = datetime.utcnow()

async def update_game_interface(game_id: int, context: CallbackContext, text: str = None):
    if game_id not in cricket_games:
        return

    game = cricket_games[game_id]
    if not text:
        try:
            batter_name = (await context.bot.get_chat(game["batter"])).first_name
            bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
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
    _, game_id = query.data.split('_')
    game_id = int(game_id)
    
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

async def handle_watch_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id = query.data.split('_')
    game_id = int(game_id)

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
    
    player1_name = (await context.bot.get_chat(game["player1"])).first_name
    player2_name = "Waiting for opponent" if not game["player2"] else (await context.bot.get_chat(game["player2"])).first_name
    
    bot_username = (await context.bot.get_me()).username
    keyboard = [[InlineKeyboardButton("🔄 Open Bot to Watch Live", url=f"https://t.me/{bot_username}")]]
    
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
    _, game_id_str, choice = query.data.split('_')
    game_id = int(game_id_str)
    
    if not await check_user_started_bot(update, context):
        return
    
    logger.info(f"Cricket Game - Toss Button: User {user_id} chose {choice} for game {game_id}")

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

    winner_name = (await context.bot.get_chat(game["toss_winner"])).first_name
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
    _, game_id_str, choice = query.data.split('_')
    game_id = int(game_id_str)
    
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
    _, game_id_str, number = query.data.split('_')
    game_id = int(game_id_str)
    number = int(number)
    
    if not await check_user_started_bot(update, context):
        return
    
    logger.info(f"Cricket Game - Play Button: User {user_id} chose number {number} for game {game_id}")

    if game_id not in cricket_games:
        logger.warning(f"Cricket Game - Play Button: Game {game_id} not found")
        await query.answer("Game expired!")
        return

    game = cricket_games[game_id]
    
    update_game_activity(game_id)
    
    if user_id == game["current_players"]["batter"] and game["batter_choice"] is None:
        game["batter_choice"] = number
        logger.info(f"Cricket Game - Play Button: Batter {user_id} chose {number}")
        await query.answer(f"Your choice: {number}")
        
        batter_name = (await context.bot.get_chat(game["batter"])).first_name 
        bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
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
        
        for spectator_id in game["spectators"]:
            try:
                await context.bot.edit_message_text(
                    chat_id=spectator_id,
                    message_id=game["message_id"].get(spectator_id),
                    text=text
                )
            except Exception as e:
                print(f"Error updating for spectator {spectator_id}: {e}")
        
        for player_id in [game["player1"], game["player2"]]:
            player_text = text
            if player_id == game["current_players"]["batter"]:
                player_text += f"\n\nYou chose: {number}"
            else:
                player_text += f"\n\n⚡ {bowler_name}, choose a number (1-6):"
            
            keyboard = []
            if player_id == game["current_players"]["bowler"]:
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
                print(f"Error updating for player {player_id}: {e}")
        
    elif user_id == game["current_players"]["bowler"] and game["bowler_choice"] is None:
        game["bowler_choice"] = number
        logger.info(f"Cricket Game - Play Button: Bowler {user_id} chose {number}")
        await query.answer(f"Your choice: {number}")
        
        batter_choice = game["batter_choice"]
        bowler_choice = number
        
        logger.info(f"Cricket Game - Play Button: Ball result - Batter: {batter_choice}, Bowler: {bowler_choice}")
        
        game["batter_choice"] = None
        game["bowler_choice"] = None

        batter_name = (await context.bot.get_chat(game["batter"])).first_name
        bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
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
                    print(f"Error updating participant {participant_id}: {e}")
            
            await handle_wicket(game_id, context)
            return
        else:
            runs = batter_choice
            result_text = f"🎯 Ball Result: {runs} RUNS!\nBatter: {batter_choice} | Bowler: {bowler_choice}"
            if game["innings"] == 1:
                game["score1"] += runs
            else:
                game["score2"] += runs
            game["match_details"].append((game["over"], game["ball"], runs, False))
            
            game["ball"] += 1
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0

            if game["innings"] == 2 and game["score2"] >= game["target"]:
                score = game['score1'] if game['innings'] == 1 else game['score2']
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
                        print(f"Error updating participant {participant_id}: {e}")
                
                await declare_winner(game_id, context)
                return
            elif game["over"] >= game["max_overs"]:
                score = game['score1'] if game['innings'] == 1 else game['score2']
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
                        print(f"Error updating participant {participant_id}: {e}")
                
                await end_innings(game_id, context)
                return

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
        
        for participant_id in list(game["spectators"]) + [game["player1"], game["player2"]]:
            try:
                participant_text = text
                participant_keyboard = None
                
                if participant_id == game["current_players"]["batter"]:
                    participant_keyboard = InlineKeyboardMarkup(keyboard)
                    
                await context.bot.edit_message_text(
                    chat_id=participant_id,
                    message_id=game["message_id"].get(participant_id),
                    text=participant_text,
                    reply_markup=participant_keyboard
                )
            except Exception as e:
                print(f"Error updating participant {participant_id}: {e}")
    else:
        logger.info(f"Cricket Game - Play Button: User {user_id} tried to play out of turn")
        await query.answer("Not your turn!")
        return

async def handle_wicket(game_id: int, context: CallbackContext):
    if game_id not in cricket_games:
        return

    game = cricket_games[game_id]
    update_game_activity(game_id)
    
    game["ball"] += 1
    if game["ball"] == 6:
        game["over"] += 1
        game["ball"] = 0

    if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
        game["batter_choice"] = None
        game["bowler_choice"] = None
        await end_innings(game_id, context)
        return
    
    try:
        batter_name = (await context.bot.get_chat(game["batter"])).first_name
        bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
    except Exception as e:
        logger.error(f"Error retrieving player information: {e}")
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text="Error retrieving player information.")
        return

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
    
    game["batter_choice"] = None
    game["bowler_choice"] = None
    
    await update_game_interface(game_id, context, text)

async def end_innings(game_id: int, context: CallbackContext):
    if game_id not in cricket_games:
        return

    game = cricket_games[game_id]
    
    if game["innings"] == 1:
        game["innings"] = 2
        game["target"] = game["score1"] + 1
        
        game["batter"], game["bowler"] = game["bowler"], game["batter"]
        game["current_players"] = {
            "batter": game["batter"],
            "bowler": game["bowler"]
        }
        
        game["wickets"] = 0
        game["over"] = 0
        game["ball"] = 0
        game["score2"] = 0
        
        try:
            batter_name = (await context.bot.get_chat(game["batter"])).first_name
            bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
        except Exception:
            await context.bot.send_message(
                chat_id=game["group_chat_id"],
                text="Error retrieving player information.")
            return

        spectator_count = len(game["spectators"])
        spectator_text = f"👁️ {spectator_count}" if spectator_count > 0 else ""
        
        text = (
            f"🔥 *INNINGS BREAK* 🔥\n\n"
            f"First innings score: {game['score1']}\n"
            f"Target: {game['target']} runs\n"
            f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
            f"🔸 Now batting: {batter_name}\n"
            f"🔹 Now bowling: {bowler_name}\n\n"
            f"⚡ {batter_name}, choose a number (1-6):"
        )
        
        game["batter_choice"] = None
        game["bowler_choice"] = None
        
        await update_game_interface(game_id, context, text)
    else:
        await declare_winner(game_id, context)

async def declare_winner(game_id: int, context: CallbackContext):
    if game_id not in cricket_games:
        return

    game = cricket_games[game_id]

    # Player name fallback
    try:
        p1 = (await context.bot.get_chat(game["player1"])).first_name
        p2 = (await context.bot.get_chat(game["player2"])).first_name
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
                winner = (await context.bot.get_chat(winner_id)).first_name
            except:
                winner = "Player"
            result = f"🏅 {winner} won by {game['max_wickets'] - game['wickets']} wicket(s)!"
            if game["wickets"] == 0:
                await check_special_achievement(game_id, "perfect_match", context, winner_id)
        else:
            winner_id = game["bowler"]
            loser_id = game["batter"]
            try:
                winner = (await context.bot.get_chat(winner_id)).first_name
            except:
                winner = "Player"
            diff = game["target"] - game["score2"] - 1
            result = f"🏅 {winner} won by {diff} runs!"
    else:
        result = "Match ended unexpectedly!"

    # ✅ Accurate name-score mapping
    score_summary = ""
    player1_id = str(game["player1"])
    player2_id = str(game["player2"])
    scores = {player1_id: game["score1"], player2_id: game["score2"]}

    try:
        name1 = (await context.bot.get_chat(player1_id)).first_name
    except:
        name1 = "Player 1"
    try:
        name2 = (await context.bot.get_chat(player2_id)).first_name
    except:
        name2 = "Player 2"

    score_summary += f"🧑 {name1}: {scores[player1_id]} runs\n"
    score_summary += f"🧑 {name2}: {scores[player2_id]} runs\n"

    result_message = (
        f"🏆 *GAME OVER!*\n\n"
        f"📜 *Match Summary:*\n"
        f"{score_summary}\n"
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
                await context.bot.deleteMessage(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id)
                )
        except Exception as e:
            logger.error(f"Error sending result to {player_id}: {e}")

    # ✅ Update stats in DB
    if winner_id and loser_id:
        winner_id_str = str(winner_id)
        loser_id_str = str(loser_id)

        winner_runs = game['score2'] if winner_id == game["batter"] else game['score1']
        loser_runs = game['score1'] if winner_id == game["batter"] else game['score2']

        # 🏏 Wickets logic
        wickets_taken_by_winner = game["wickets"] if winner_id == game["bowler"] else 0
        wickets_taken_by_loser = game["wickets"] if loser_id == game["bowler"] else 0

        # 🟢 Update winner
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

        # 🔴 Update loser
        user_collection.update_one(
            {"user_id": loser_id_str},
            {"$inc": {
                "stats.losses": 1,
                "stats.runs": loser_runs,
                "stats.wickets": wickets_taken_by_loser
            },
            "$set": {
                "stats.current_streak": 0,
                "stats.last_result": "loss"
            }},
            upsert=True
        )

        # 🏅 Check achievements
        await check_achievements(winner_id, context)
        await check_achievements(loser_id, context)

        # 🗃️ Save match history
        try:
            game_collection.insert_one({
                "timestamp": datetime.now(),
                "participants": [player1_id, player2_id],
                "scores": {
                    "player1": game["score1"],
                    "player2": game["score2"]
                },
                "winner": winner_id_str,
                "loser": loser_id_str,
                "result": result,
                "innings": game["innings"],
                "player1_opponent": player2_id,
                "player2_opponent": player1_id,
                "wickets": game["wickets"]
            })
        except Exception as e:
            logger.error(f"Error saving game history: {e}")

    # Clean up memory
    reminder_sent.pop(game_id, None)
    game_activity.pop(game_id, None)
    cricket_games.pop(game_id, None)


async def chat_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /c <message>")
        return

    user = update.effective_user
    user_id = str(user.id)
    message = " ".join(context.args)

    if not await check_user_started_bot(update, context):
        return
    
    active_game = None
    for game_id, game in cricket_games.items():
        if user_id in [game["player1"], game["player2"]]:
            active_game = game
            break
    
    if active_game:
        chat_id = active_game.get("group_chat_id")
        if not chat_id:
            await update.message.reply_text("❌ Game chat not found.")
            return

        formatted_message = f"💬 {user.first_name}: {message}"

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=formatted_message
            )
            if update.effective_chat.type == "private":
                await update.message.delete()
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
            await update.message.reply_text("❌ Failed to send message to game chat.")
    else:
        await update.message.reply_text("❌ You are not in an active cricket game.")

def update_game_activity(game_id):
    game_activity[game_id] = datetime.now()

async def check_inactive_games(context: CallbackContext):
    current_time = datetime.now()
    
    for game_id, game in list(cricket_games.items()):
        if game_id not in game_activity or game["player2"] is not None:
            continue
            
        last_activity = game_activity.get(game_id)
        if not last_activity:
            continue
            
        if (current_time - last_activity > timedelta(seconds=20) and 
                game_id not in reminder_sent):
            
            try:
                player_name = (await context.bot.get_chat(game["player1"])).first_name
                bot_username = (await context.bot.get_me()).username
                
                reminder_text = (
                    f"🏏 *Cricket Game Reminder* 🏏\n\n"
                    f"{player_name}'s cricket game is still waiting for an opponent!\n"
                    f"Anyone want to join? Click the button below:"
                )
                
                keyboard = [[InlineKeyboardButton("🎮 Join Cricket Game", url=f"https://t.me/{bot_username}?start=game_{game_id}")]]
                
                await context.bot.send_message(
                    chat_id=game["group_chat_id"],
                    text=reminder_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                
                reminder_sent[game_id] = True
            except Exception as e:
                logger.error(f"Error sending game reminder: {e}")
                
        elif current_time - last_activity > timedelta(minutes=15):
            try:
                await context.bot.send_message(
                    chat_id=game["group_chat_id"],
                    text="The cricket game has been cancelled due to inactivity."
                )
                
                if game_id in reminder_sent:
                    del reminder_sent[game_id]
                if game_id in game_activity:
                    del game_activity[game_id]
                del cricket_games[game_id]
                
            except Exception as e:
                logger.error(f"Error cleaning up inactive game: {e}")
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
    
    keyboard = [[InlineKeyboardButton("🏆 View Achievements", callback_data="view_achievements")]]
    
    await update.message.reply_text(
        text, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def achievements_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("You need to start the bot first!")
        return
    
    await display_earned_achievements(update, context, user_id)

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
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Achievements", callback_data="view_achievements")]]
    
    await query.edit_message_text(
        text, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
    
    keyboard = [[InlineKeyboardButton("🏆 View Achievements", callback_data="view_achievements")]]
    
    await update.message.reply_text(
        text, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def achievements_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("You need to start the bot first!")
        return
    
    user_achievements = achievements_collection.find_one({"user_id": user_id})
    earned_ids = user_achievements.get("achievements", []) if user_achievements else []
    
    earned_count = len(earned_ids)
    total_count = len(ACHIEVEMENTS)
    
    text = f"🏆 *Your Achievements ({earned_count}/{total_count})*\n\n"
    
    if not earned_ids:
        text += "You haven't earned any achievements yet. Keep playing to unlock them!"
    else:
        categories = {
            "Batting": [a for a in ACHIEVEMENTS if a["requirement"]["type"] == "runs"],
            "Bowling": [a for a in ACHIEVEMENTS if a["requirement"]["type"] == "wickets"],
            "Matches": [a for a in ACHIEVEMENTS if a["requirement"]["type"] in ["matches", "wins"]],
            "Performance": [a for a in ACHIEVEMENTS if a["requirement"]["type"] in ["accuracy", "streak", "special"]]
        }
        
        for category, category_achievements in categories.items():
            category_earned = [a for a in category_achievements if a["id"] in earned_ids]
            if category_earned:
                text += f"*{category}:*\n"
                for achievement in category_earned[:3]:
                    text += f"• {achievement['name']} - {achievement['description']}\n"
                
                if len(category_earned) > 3:
                    text += f"  _...and {len(category_earned) - 3} more {category.lower()} achievements_\n"
                text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("🔒 View Locked Achievements", callback_data="locked_achievements")],
        [InlineKeyboardButton("🏆 View Leaderboard", callback_data="view_leaderboard")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def achievements_button(update: Update, context: CallbackContext) -> None:
    """Handle all achievement-related button callbacks"""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    
    user = update.effective_user
    user_id = str(user.id)
    
    if query.data == "view_achievements":
        await display_earned_achievements(update, context, user_id)
    elif query.data == "locked_achievements":
        await display_locked_achievements(update, context, user_id)
    elif query.data == "view_leaderboard":
        await leaderboard_callback(update, context)


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
    
    earned_ids = user_achievements.get("achievements", [])
    newly_earned = []
    
    matches_played = stats.get("wins", 0) + stats.get("losses", 0)
    accuracy = 0
    if matches_played > 0:
        accuracy = round((stats.get("wins", 0) / matches_played) * 100)
    
    for achievement in ACHIEVEMENTS:
        if achievement["id"] in earned_ids:
            continue
        
        achieved = False
        req_type = achievement["requirement"]["type"]
        req_value = achievement["requirement"]["value"]
        
        if req_type == "runs" and stats.get("runs", 0) >= req_value:
            achieved = True
        elif req_type == "wickets" and stats.get("wickets", 0) >= req_value:
            achieved = True
        elif req_type == "wins" and stats.get("wins", 0) >= req_value:
            achieved = True
        elif req_type == "matches" and matches_played >= req_value:
            achieved = True
        elif req_type == "accuracy" and accuracy >= req_value and matches_played >= 5:
            achieved = True
        
        if achieved:
            achievements_collection.update_one(
                {"user_id": user_id_str},
                {"$addToSet": {"achievements": achievement["id"]}}
            )
            
            newly_earned.append(achievement)
            
            if context and hasattr(context, "bot"):
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🏆 *Achievement Unlocked!*\n\n*{achievement['name']}*\n{achievement['description']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error sending achievement notification: {e}")
    
    return newly_earned

async def check_special_achievement(game_id, achievement_type, context, user_id=None):
    if game_id not in cricket_games:
        return
    
    game = cricket_games[game_id]
    
    if not user_id:
        if achievement_type == "perfect_match":
            user_id = game["batter"] if game["innings"] == 2 and game["score2"] >= game["target"] and game["wickets"] == 0 else None
        elif achievement_type == "tie":
            if game["score1"] == game["score2"]:
                await check_special_achievement(game_id, "tie", context, game["player1"])
                await check_special_achievement(game_id, "tie", context, game["player2"])
                return
        elif achievement_type == "comeback":
            # Example logic: if player was behind by 20+ runs in first innings but won
            if game["innings"] == 2 and game["score2"] >= game["target"] and (game["target"] - game["score1"]) >= 20:
                user_id = game["player2"]
    
    if not user_id:
        return
        
    user_id_str = str(user_id)
    
    user_achievements = achievements_collection.find_one({"user_id": user_id_str})
    if not user_achievements:
        user_achievements = {"user_id": user_id_str, "achievements": []}
        achievements_collection.insert_one(user_achievements)
    
    achievement = next((a for a in ACHIEVEMENTS if a["requirement"]["type"] == "special" 
                       and a["requirement"]["value"] == achievement_type), None)
    
    if not achievement or achievement["id"] in user_achievements.get("achievements", []):
        return
    
    achievements_collection.update_one(
        {"user_id": user_id_str},
        {"$addToSet": {"achievements": achievement["id"]}}
    )
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🏆 *Special Achievement Unlocked!*\n\n*{achievement['name']}*\n{achievement['description']}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error sending special achievement notification: {e}")

async def display_locked_achievements(update: Update, context: CallbackContext, user_id: str) -> None:
    """Display locked achievements with proper message handling"""
    user_achievements = achievements_collection.find_one({"user_id": user_id})
    earned_ids = user_achievements.get("achievements", []) if user_achievements else []
    
    locked = [a for a in ACHIEVEMENTS if a["id"] not in earned_ids]
    
    if not locked:
        text = "🎉 Congratulations! You've unlocked all achievements!"
    else:
        categories = {
            "Batting": [a for a in locked if a["requirement"]["type"] == "runs"],
            "Bowling": [a for a in locked if a["requirement"]["type"] == "wickets"],
            "Matches": [a for a in locked if a["requirement"]["type"] in ["matches", "wins"]],
            "Performance": [a for a in locked if a["requirement"]["type"] in ["accuracy", "streak", "special"]]
        }
        
        text = "🔒 *Locked Achievements*\n\n"
        
        for category, category_achievements in categories.items():
            if category_achievements:
                text += f"*{category}:*\n"
                for achievement in category_achievements[:3]:
                    text += f"• {achievement['name']} - {achievement['description']}\n"
                
                if len(category_achievements) > 3:
                    text += f"  _...and {len(category_achievements) - 3} more {category.lower()} achievements_\n"
                text += "\n"
    
    keyboard = [[InlineKeyboardButton("🏆 View Earned Achievements", callback_data="view_achievements")]]
    
    try:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error displaying locked achievements: {e}")
        await update.callback_query.edit_message_text(
            "Error displaying all locked achievements. You have many more to unlock!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def display_earned_achievements(update: Update, context: CallbackContext, user_id: str) -> None:
    """Display earned achievements with proper message handling for both command and callback"""
    user_achievements = achievements_collection.find_one({"user_id": user_id})
    earned_ids = user_achievements.get("achievements", []) if user_achievements else []
    
    earned_count = len(earned_ids)
    total_count = len(ACHIEVEMENTS)
    
    text = f"🏆 *Your Achievements ({earned_count}/{total_count})*\n\n"
    
    if not earned_ids:
        text += "You haven't earned any achievements yet. Keep playing to unlock them!"
    else:
        categories = {
            "Batting": [a for a in ACHIEVEMENTS if a["requirement"]["type"] == "runs" and a["id"] in earned_ids],
            "Bowling": [a for a in ACHIEVEMENTS if a["requirement"]["type"] == "wickets" and a["id"] in earned_ids],
            "Matches": [a for a in ACHIEVEMENTS if a["requirement"]["type"] in ["matches", "wins"] and a["id"] in earned_ids],
            "Performance": [a for a in ACHIEVEMENTS if a["requirement"]["type"] in ["accuracy", "streak", "special"] and a["id"] in earned_ids]
        }
        
        for category, category_achievements in categories.items():
            if category_achievements:
                text += f"*{category}:*\n"
                for achievement in category_achievements[:3]:
                    text += f"• {achievement['name']} - {achievement['description']}\n"
                
                if len(category_achievements) > 3:
                    text += f"  _...and {len(category_achievements) - 3} more {category.lower()} achievements_\n"
                text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("🔒 View Locked Achievements", callback_data="locked_achievements")],
        [InlineKeyboardButton("🏆 View Leaderboard", callback_data="view_leaderboard")]
    ]
    
    # Handle both direct command and callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
def setup_jobs(application):
    job_queue = application.job_queue
    job_queue.run_repeating(check_inactive_games, interval=30, first=10)
    job_queue.run_repeating(send_inactive_player_reminder, interval=5, first=5)

def get_cricket_handlers():
    return [
        CommandHandler("stats", stats),
        CommandHandler("achievements", achievements_command),
        CommandHandler("leaderboard", leaderboard),
        CommandHandler("history", game_history),
        CommandHandler("chat", chat_command),
        CallbackQueryHandler(toss_button, pattern="^toss_"),
        CallbackQueryHandler(choose_button, pattern="^choose_"),
        CallbackQueryHandler(play_button, pattern="^play_"),
        CallbackQueryHandler(handle_join_button, pattern=r"^join_"),
        CallbackQueryHandler(handle_watch_button, pattern=r"^watch_"),
        CallbackQueryHandler(achievements_button, pattern=r"^view_achievements$|^locked_achievements$|^view_leaderboard$"),
    ]
