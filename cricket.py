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


# Add this near the top of your file with other MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
user_collection = db["users"]
game_collection = db["games"]
       

cricket_games = {}
reminder_sent = {}
game_activity = {}

def generate_game_code():
    return str(random.randint(100, 999))

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
                
            # Validate inputs
            if max_overs < 1:
                max_overs = 1
            if max_wickets < 1:
                max_wickets = 1
                
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Invalid parameters! Format: /chatcricket [overs] [wickets]")
            return
    
    game_id = chat_id
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
        "last_reminder": None  # Track when the last reminder was sent
    }
    for old_game_id, old_game in list(cricket_games.items()):
    if old_game.get("player1") == user.id and old_game.get("player2") is None:
        try:
            await context.bot.send_message(
                chat_id=old_game.get("group_chat_id"),
                text="⚠️ This cricket game has expired as the creator started a new game.")
            
            # Clean up old game data
            if old_game_id in reminder_sent:
                del reminder_sent[old_game_id]
            if old_game_id in game_activity:
                del game_activity[old_game_id]
            del cricket_games[old_game_id]
        except Exception as e:
            logger.error(f"Error cleaning up old game: {e}")
    
    update_game_activity(game_id)
    
    # Create game description with overs/wickets
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


        cricket_games[game_id]["original_message_id"] = sent_message.message_id
    

    try:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=game_desc,
            reply_markup=keyboard,
            parse_mode="Markdown")
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Error creating game: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Error creating the game. Please try again later.")

async def send_inactive_player_reminder(context: CallbackContext) -> None:
    """Send reminders to inactive players during games"""
    current_time = datetime.utcnow()
    
    for game_id, game in list(cricket_games.items()):
        # Skip games that are waiting for a second player
        if game["player2"] is None:
            continue
            
        # Skip games that don't have an active turn in progress
        if game["batter"] is None or game["bowler"] is None:
            continue
            
        # Determine which player should make a move
        current_player_id = None
        if game["batter_choice"] is None:
            current_player_id = game["current_players"]["batter"]
        elif game["bowler_choice"] is None:
            current_player_id = game["current_players"]["bowler"]
        else:
            continue  # No pending moves
        
        # Check if it's been at least 10 seconds since last activity and no reminder sent in last 10 seconds
        last_activity = game_activity.get(game_id, datetime.utcnow())
        last_reminder = game.get("last_reminder")
        
        if (current_time - last_activity).total_seconds() >= 10 and (
                last_reminder is None or (current_time - last_reminder).total_seconds() >= 10):
            
            try:
                # Get player names
                player_name = (await context.bot.get_chat(current_player_id)).first_name
                
                # Send DM reminder
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
                
                # Update reminder timestamp
                game["last_reminder"] = current_time
                
            except Exception as e:
                logger.error(f"Error sending play reminder: {e}")

# Update the update_game_activity function to include last move
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
            f"⏳ Over: {game['over']}.{game['ball']}    {spectator_text}\n"
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
    
    await context.bot.send_message(
        chat_id=game["group_chat_id"],
        text=f"🎉 {query.from_user.first_name} joined the game!\n\n"
             f"Players should open the bot to continue the game:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
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
    
    # Convert game_id to integer since chat_ids are integers
    game_id = int(game_id_str)
    
    # Check if the user has started the bot
    if not await check_user_started_bot(update, context):
        return  # Exit if the user hasn't started the bot
    
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
    
    # Convert game_id to integer
    game_id = int(game_id_str)
    
    # Check if the user has started the bot
    if not await check_user_started_bot(update, context):
        return  # Exit if the user hasn't started the bot
    
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
    
    # Convert game_id and number to integers
    game_id = int(game_id_str)
    number = int(number)
    
    # Check if the user has started the bot
    if not await check_user_started_bot(update, context):
        return  # Exit if the user hasn't started the bot
    
    logger.info(f"Cricket Game - Play Button: User {user_id} chose number {number} for game {game_id}")

    if game_id not in cricket_games:
        logger.warning(f"Cricket Game - Play Button: Game {game_id} not found")
        await query.answer("Game expired!")
        return

    game = cricket_games[game_id]
    
    # Update activity timestamp when a move is made
    update_game_activity(game_id)
    
    # Validate player turn
    if user_id == game["current_players"]["batter"] and game["batter_choice"] is None:
        game["batter_choice"] = number
        logger.info(f"Cricket Game - Play Button: Batter {user_id} chose {number}")
        await query.answer(f"Your choice: {number}")
        
        # Update game interface after batter's choice - DON'T REVEAL BATTER'S CHOICE
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
        
        # Send updated interface to spectators
        for spectator_id in game["spectators"]:
            try:
                await context.bot.edit_message_text(
                    chat_id=spectator_id,
                    message_id=game["message_id"].get(spectator_id),
                    text=text
                )
            except Exception as e:
                print(f"Error updating for spectator {spectator_id}: {e}")
        
        # Send updated interface to players with appropriate buttons
        for player_id in [game["player1"], game["player2"]]:
            player_text = text
            if player_id == game["current_players"]["batter"]:
                player_text += f"\n\nYou chose: {number}"
            else:
                player_text += f"\n\n⚡ {bowler_name}, choose a number (1-6):"
            
            # Create keyboard for bowler only
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
        
        # Process the result now that both players have chosen
        batter_choice = game["batter_choice"]
        bowler_choice = number
        
        logger.info(f"Cricket Game - Play Button: Ball result - Batter: {batter_choice}, Bowler: {bowler_choice}")
        
        # Reset choices for next ball
        game["batter_choice"] = None
        game["bowler_choice"] = None

        # Get player names
        batter_name = (await context.bot.get_chat(game["batter"])).first_name
        bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
        score = game['score1'] if game['innings'] == 1 else game['score2']
        target = game['target'] if game['innings'] == 2 else None
        spectator_count = len(game["spectators"])
        spectator_text = f"👁️ {spectator_count}" if spectator_count > 0 else ""

        # Process ball result
        if batter_choice == bowler_choice:
            result_text = f"🎯 Ball Result: WICKET!\nBatter: {batter_choice} | Bowler: {bowler_choice}"
            game["wickets"] += 1
            game["match_details"].append((game["over"], game["ball"], 0, True))
            
            # Update interface with wicket result
            text = (
                f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
                f"🔸 Batting: {batter_name}\n"
                f"🔹 Bowling: {bowler_name}\n"
                f"📊 Score: {score}/{game['wickets']}\n\n"
                f"{result_text}"
            )
            
            # Update all participants with result
            for participant_id in list(game["spectators"]) + [game["player1"], game["player2"]]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=participant_id,
                        message_id=game["message_id"].get(participant_id),
                        text=text
                    )
                except Exception as e:
                    print(f"Error updating participant {participant_id}: {e}")
            
            # Handle wicket
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
            
            # Update ball count
            game["ball"] += 1
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0

            # Check end conditions
            if game["innings"] == 2 and game["score2"] >= game["target"]:
                # Update score first
                score = game['score1'] if game['innings'] == 1 else game['score2']
                text = (
                    f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
                    f"🔸 Batting: {batter_name}\n"
                    f"🔹 Bowling: {bowler_name}\n"
                    f"📊 Score: {score}/{game['wickets']}\n\n"
                    f"{result_text}"
                )
                
                # Update all participants with result
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
                # Update score first
                score = game['score1'] if game['innings'] == 1 else game['score2']
                text = (
                    f"⏳ Over: {game['over']}.{game['ball']}  {spectator_text}\n"
                    f"🔸 Batting: {batter_name}\n"
                    f"🔹 Bowling: {bowler_name}\n"
                    f"📊 Score: {score}/{game['wickets']}\n\n"
                    f"{result_text}"
                )
                
                # Update all participants with result
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

        # Update score after runs
        score = game['score1'] if game['innings'] == 1 else game['score2']
        
        # Build updated interface
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
            row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_id}_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_id}")])
        
        # Update all participants
        for participant_id in list(game["spectators"]) + [game["player1"], game["player2"]]:
            try:
                participant_text = text
                participant_keyboard = None
                
                # Only show action buttons to the current batter
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
    update_game_activity(game_id)  # Update activity timestamp
    
    game["ball"] += 1
    if game["ball"] == 6:
        game["over"] += 1
        game["ball"] = 0

    if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
        # Reset choices before ending innings
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
    
    # Ensure choices are reset
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
            f"Target: {game['target']} runs\n\n"
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
    try:
        p1 = (await context.bot.get_chat(game["player1"])).first_name
        p2 = (await context.bot.get_chat(game["player2"])).first_name
    except Exception as e:
        logger.error(f"Error retrieving player names: {e}")
        p1 = "Player 1"
        p2 = "Player 2"

    if game["score1"] == game["score2"]:
        result = "🤝 Match Drawn!"
        winner_id = None
        loser_id = None
    elif game["innings"] == 2:
        if game["score2"] >= game["target"]:
            winner_id = game["batter"]
            loser_id = game["bowler"]
            try:
                winner = (await context.bot.get_chat(winner_id)).first_name
            except:
                winner = "Player"
            result = f"🏅 {winner} won by {game['max_wickets'] - game['wickets']} wicket(s)!"
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
        winner_id = None
        loser_id = None

    result_message = (
        f"🏆 *GAME OVER!*\n\n"
        f"📜 *Match Summary:*\n"
        f"🧑 {p1}: {game['score1']} runs\n"
        f"🧑 {p2}: {game['score2']} runs\n\n"
        f"{result}"
    )

    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=result_message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error sending result to group chat: {e}")

    participants = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in participants:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=result_message,
                parse_mode="Markdown"
            )
            
            try:
                if player_id in game["message_id"]:
                    await context.bot.deleteMessage(
                        chat_id=player_id,
                        message_id=game["message_id"].get(player_id)
                    )
            except Exception as e:
                logger.error(f"Error deleting game message for {player_id}: {e}")
                
        except Exception as e:
            logger.error(f"Error sending result to {player_id}: {e}")

    # Update player statistics if a winner is determined
    if winner_id and loser_id:
        # Update winner's stats
        winner_stats = user_collection.find_one({"user_id": str(winner_id)}, {"_id": 0, "stats": 1})
        if winner_stats and "stats" in winner_stats:
            user_collection.update_one(
                {"user_id": str(winner_id)},
                {"$inc": {"stats.wins": 1, "stats.runs": game['score2'] if winner_id == game["batter"] else game['score1']}}
            )
        else:
            user_collection.update_one(
                {"user_id": str(winner_id)},
                {"$set": {"stats": {"wins": 1, "losses": 0, "runs": game['score2'] if winner_id == game["batter"] else game['score1'], "wickets": 0, "accuracy": 0}}},
                upsert=True
            )
        
        # Update loser's stats
        loser_stats = user_collection.find_one({"user_id": str(loser_id)}, {"_id": 0, "stats": 1})
        if loser_stats and "stats" in loser_stats:
            user_collection.update_one(
                {"user_id": str(loser_id)},
                {"$inc": {"stats.losses": 1}}
            )
        else:
            user_collection.update_one(
                {"user_id": str(loser_id)},
                {"$set": {"stats": {"wins": 0, "losses": 1, "runs": 0, "wickets": 0, "accuracy": 0}}},
                upsert=True
            )

        try:
            game_collection.insert_one({
                "timestamp": datetime.now(),
                "participants": [str(game["player1"]), str(game["player2"])],  # Convert to strings
                "scores": {"player1": game["score1"], "player2": game["score2"]},
                "result": result,
                "innings": game["innings"],
                # Store opponent info for each player
                "player1_opponent": str(game["player2"]),
                "player2_opponent": str(game["player1"])
            })
        except Exception as e:
            logger.error(f"Error saving game history: {e}")

    # Clean up game data
    if game_id in reminder_sent:
        del reminder_sent[game_id]
    if game_id in game_activity:
        del game_activity[game_id]
    del cricket_games[game_id]

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
                
                # In the check_inactive_games function, modify the keyboard creation:
                keyboard = [[InlineKeyboardButton("🎮 Join Cricket Game", 
                                url=f"https://t.me/{bot_username}?start=game_{game_id}"
                                if game.get("player2") is None else
                                f"https://t.me/c/{str(game['group_chat_id'])[4:]}/{game.get('original_message_id')}")]]
                
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

async def stats(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    user_data = user_collection.find_one({"user_id": user_id})

    if not user_data:
        await update.message.reply_text("You need to start the bot first!")
        return
    
    # Fetch player statistics
    stats_data = user_collection.find_one({"user_id": user_id}, {"_id": 0, "stats": 1})
    if not stats_data or "stats" not in stats_data:
        await update.message.reply_text("No statistics available yet. Play some games to see your stats!")
        return
    
    stats = stats_data["stats"]
    text = f"📊 *Your Statistics:*\n\n"
    text += f"🏆 Wins: {stats.get('wins', 0)}\n"
    text += f"-losses: {stats.get('losses', 0)}\n"
    text += f"🏃 Runs: {stats.get('runs', 0)}\n"
    text += f"⚾ Wickets: {stats.get('wickets', 0)}\n"
    text += f"🎯 Accuracy: {stats.get('accuracy', 0)}%"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def leaderboard(update: Update, context: CallbackContext) -> None:
    # Fetch top players
    top_players = user_collection.find({}, {"_id": 0, "user_id": 1, "first_name": 1, "stats": 1}) \
                                .sort([("stats.wins", -1), ("stats.runs", -1)]) \
                                .limit(10)
    
    text = "🏆 *Leaderboard:*\n\n"
    for idx, player in enumerate(top_players, 1):
        stats = player.get("stats", {})
        text += f"{idx}. {player.get('first_name', 'Unknown')} - Wins: {stats.get('wins', 0)}, Runs: {stats.get('runs', 0)}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def game_chat(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /chat <message>")
        return
    
    user = update.effective_user
    message = " ".join(context.args)
    
    # Find the active game for this user
    active_game = None
    for game_id, game in cricket_games.items():
        if user.id in [game["player1"], game["player2"]]:
            active_game = game
            break
    
    if not active_game:
        await update.message.reply_text("You are not in an active game.")
        return
    
    # Send message to all participants
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
    user_id = str(user.id)  # Ensure user_id is a string
    
    # Add game_collection definition if it doesn't exist already
    try:
        from pymongo import MongoClient
        db = client['telegram_bot']
        game_collection = db["games"]
        
        # Fetch game history with proper query
        history = list(game_collection.find(
            {"$or": [
                {"participants": {"$in": [user_id]}},
                {"player1_opponent": user_id},
                {"player2_opponent": user_id}
            ]}
        ).sort("timestamp", -1).limit(5))
        
        if not history:
            await update.message.reply_text("You haven't played any games yet!")
            return
        
        text = "📜 *Your Game History:*\n\n"
        for idx, game in enumerate(history, 1):
            # Format timestamp
            timestamp_str = game.get('timestamp', datetime.now()).strftime("%Y-%m-%d %H:%M")
            
            # Determine opponent
            participants = game.get('participants', [])
            opponent_id = None
            for participant in participants:
                if participant != user_id:
                    opponent_id = participant
                    break
            
            # If we didn't find opponent in participants, check the dedicated fields
            if not opponent_id:
                if game.get('player1_opponent') == user_id:
                    opponent_id = game.get('player1')
                elif game.get('player2_opponent') == user_id:
                    opponent_id = game.get('player2')
            
            # Try to get opponent's name from database or use default
            opponent_name = "Unknown"
            if opponent_id:
                opponent_data = user_collection.find_one({"user_id": opponent_id})
                if opponent_data:
                    opponent_name = opponent_data.get('first_name', 'Unknown')
            
            # Get scores
            scores = game.get('scores', {})
            user_score = scores.get('player1', 0) if user_id == game.get('participants', [])[0] else scores.get('player2', 0)
            opponent_score = scores.get('player2', 0) if user_id == game.get('participants', [])[0] else scores.get('player1', 0)
            
            # Format result
            result = game.get('result', 'No result')
            
            text += f"*Game {idx}:*\n"
            text += f"📅 Date: {timestamp_str}\n"
            text += f"👤 Opponent: {opponent_name}\n"
            text += f"🏏 Your Score: {user_score}\n"
            text += f"🏏 Opponent Score: {opponent_score}\n"
            text += f"📝 Result: {result}\n\n"
        
        await update.message.reply_text(text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error retrieving game history: {e}")
        await update.message.reply_text("An error occurred while retrieving your game history. Please try again later.")
def setup_jobs(application):
    # Check for inactive games every 30 seconds
    job_queue = application.job_queue
    job_queue.run_repeating(check_inactive_games, interval=30, first=10)
    
    # Send reminders to inactive players every 5 seconds
    job_queue.run_repeating(send_inactive_player_reminder, interval=5, first=5)

def get_cricket_handlers():
    return [
        CommandHandler("stats", stats),
        CommandHandler("leaderboard", leaderboard),
        CommandHandler("chat", chat_command),  # Use the correct function name
        CallbackQueryHandler(toss_button, pattern="^toss_"),
        CallbackQueryHandler(choose_button, pattern="^choose_"),
        CallbackQueryHandler(play_button, pattern="^play_"),
        CallbackQueryHandler(handle_join_button, pattern=r"^join_"),
        CallbackQueryHandler(handle_watch_button, pattern=r"^watch_"),
    ]
