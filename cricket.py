from pymongo import MongoClient
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters

# MongoDB connection
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
user_collection = db["users"]
cricket_games = {}

def generate_game_code():
    return str(random.randint(100, 999))

async def chat_cricket(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Check if user exists in database
    user_data = user_collection.find_one({"user_id": str(user.id)})
    if not user_data:
        # If user is not in the database, prompt them to start the bot
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("Start Bot", url=f"https://t.me/Linkingtie_bot?start=start")]]
        await update.message.reply_text(
            "⚠️ You need to start the bot first to create a match!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # If user is in the database, proceed with creating the game
    game_code = generate_game_code()
    
    while game_code in cricket_games:
        game_code = generate_game_code()

    cricket_games[game_code] = {
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
        "match_details": [],  # Track match details
        "wickets": 0,  # Track wickets
        "spectators": set(),  # Track spectators
    }

    # Create a "Join Game" button with a deep link
    join_button = InlineKeyboardButton("Join Game", url=f"https://t.me/Linkingtie_bot?start={game_code}")
    keyboard = InlineKeyboardMarkup([[join_button]])

    # Send the game message and pin it
    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *Game Started!*\nCode: `{game_code}`\n\n"
             f"To join, use `/join {game_code}` or click the button below:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.message_id)


async def watch_game(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    game_code = context.args[0] if context.args else None

    if not game_code or game_code not in cricket_games:
        await update.message.reply_text("Invalid code!")
        return

    game = cricket_games[game_code]
    
    if user_id in [game["player1"], game["player2"]]:
        await update.message.reply_text("You're already a player!")
        return

    if user_id in game["spectators"]:
        await update.message.reply_text("Already spectating!")
        return

    # Create new message for spectator
    try:
        msg = await context.bot.send_message(
            chat_id=user_id,
            text="🚀 Connecting to game..."
        )
        game["message_id"][user_id] = msg.message_id  # Store spectator's message ID
        game["spectators"].add(user_id)
        await update_game_interface(game_code, context, user_id)
        await update.message.reply_text("✅ Now spectating! Updates will appear here.")
    except Exception as e:
        print(f"Spectator error: {e}")
        await update.message.reply_text("❌ Failed to join as spectator")
    user_id = update.effective_user.id
    game_code = context.args[0] if context.args else None

    if not game_code or game_code not in cricket_games:
        await update.message.reply_text("Invalid code!")
        return

    game = cricket_games[game_code]
    if user_id in [game["player1"], game["player2"]]:
        await update.message.reply_text("You are already a player in this game!")
        return

    if user_id in game["spectators"]:
        await update.message.reply_text("You are already spectating this game!")
        return

    # Add user to spectators
    game["spectators"].add(user_id)

    # Send initial game interface to spectator
    await update_game_interface(game_code, context, user_id)

    await update.message.reply_text("You are now spectating the game. You will receive updates in this chat.")

async def join_cricket(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    game_code = context.args[0] if context.args else None

    if not game_code or game_code not in cricket_games:
        await update.message.reply_text("Invalid code!")
        return

    game = cricket_games[game_code]
    
    # Prevent self-joining
    if user_id == game["player1"]:
        await update.message.reply_text("You can't join your own game!")
        return

    if game["player2"]:
        await update.message.reply_text("Game full!")
        return

    game["player2"] = user_id
    p1_name = (await context.bot.get_chat(game["player1"])).first_name

    keyboard = [[
        InlineKeyboardButton("Heads", callback_data=f"toss_{game_code}_heads"),
        InlineKeyboardButton("Tails", callback_data=f"toss_{game_code}_tails")
    ]]

    for player_id in [game["player1"], game["player2"]]:
        msg = await context.bot.send_message(
            chat_id=player_id,
            text=f"⚡ Toss Time!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        game["message_id"][player_id] = msg.message_id

async def toss_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_code, choice = query.data.split('_')

    if game_code not in cricket_games:
        await query.answer("Game expired!")
        return

    game = cricket_games[game_code]
    if game["toss_winner"]:
        await query.answer("Toss done!")
        return

    toss_result = random.choice(['heads', 'tails'])
    game["toss_winner"] = user_id if choice == toss_result else game["player2"] if user_id == game["player1"] else game["player1"]

    winner_name = (await context.bot.get_chat(game["toss_winner"])).first_name
    keyboard = [[
        InlineKeyboardButton("🏏 Bat", callback_data=f"choose_{game_code}_bat"),
        InlineKeyboardButton("🎯 Bowl", callback_data=f"choose_{game_code}_bowl")
    ]]

    for player_id in [game["player1"], game["player2"]]:
        await context.bot.edit_message_text(
            chat_id=player_id,
            message_id=game["message_id"][player_id],
            text=f"{winner_name} won toss!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def choose_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_code, choice = query.data.split('_')

    if game_code not in cricket_games:
        await query.answer("Game expired!")
        return

    game = cricket_games[game_code]
    if user_id != game["toss_winner"]:
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

    await update_game_interface(game_code, context)

async def update_game_interface(game_code: str, context: CallbackContext, spectator_id=None):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    batter_name = (await context.bot.get_chat(game["batter"])).first_name
    bowler_name = (await context.bot.get_chat(game["bowler"])).first_name

    over_display = f"{game['over']}.{game['ball']}" if game['ball'] != 0 else f"{game['over']}.0"
    score = game['score1'] if game['innings'] == 1 else game['score2']
    target = game['target'] if game['innings'] == 2 else None

    if game["batter_choice"] is None:
        text = (
            f"🏏 {batter_name} vs {bowler_name}\n"
            f"📊 Score: {score}\n"
            f"⏳ Over: {over_display}\n"
            f"🔸 Batting: {batter_name}\n"
            f"🔹 Bowling: {bowler_name}\n\n"
            f"⚡ {batter_name}, choose a number (1-6):"
        )
    else:
        text = (
            f"🏏 {batter_name} vs {bowler_name}\n"
            f"📊 Score: {score}\n"
            f"⏳ Over: {over_display}\n"
            f"🔸 Batting: {batter_name}\n"
            f"🔹 Bowling: {bowler_name}\n\n"
            f"⚡ {bowler_name}, choose a number (1-6):"
        )

    if target:
        text += f"\n🎯 Target: {target}"

    # Create the keyboard with buttons
    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])

    # Send updates to players and spectators
    recipients = list(game["spectators"]) + [game["player1"], game["player2"]]
    if spectator_id:
        recipients = [spectator_id]

    for player_id in recipients:
        try:
            await context.bot.edit_message_text(
                chat_id=player_id,
                message_id=game["message_id"].get(player_id),
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),  # Include the reply_markup
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error updating game interface for {player_id}: {e}")
   

async def play_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_code, number = query.data.split('_')
    number = int(number)

    if game_code not in cricket_games:
        await query.answer("Game expired!")
        return

    game = cricket_games[game_code]
    
    # Validate player turn
    if user_id == game["current_players"]["batter"] and game["batter_choice"] is None:
        game["batter_choice"] = number
        await query.answer(f"Your choice: {number}")
    elif user_id == game["current_players"]["bowler"] and game["bowler_choice"] is None:
        game["bowler_choice"] = number
        await query.answer(f"Your choice: {number}")
    else:
        await query.answer("Not your turn!")
        return

    if game["batter_choice"] is not None and game["bowler_choice"] is not None:
        batter_choice = game["batter_choice"]
        bowler_choice = game["bowler_choice"]
        game["batter_choice"] = None
        game["bowler_choice"] = None

        # Handle wicket logic
        if batter_choice == bowler_choice:
            # Batter is out
            game["wickets"] += 1
            game["match_details"].append((game["over"], game["ball"], 0, True))
            
            # End innings if wicket falls
            await handle_wicket(game_code, context)
        else:
            # Add runs to current innings
            runs = batter_choice
            if game["innings"] == 1:
                game["score1"] += runs
            else:
                game["score2"] += runs
                
            game["match_details"].append((game["over"], game["ball"], runs, False))
            game["ball"] += 1
            
            # Handle over completion
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0

            # Check target in second innings
            if game["innings"] == 2 and game["score2"] >= game["target"]:
                await declare_winner(game_code, context)
                return

        await update_game_interface(game_code, context)

async def handle_wicket(game_code: str, context: CallbackContext):
    game = cricket_games[game_code]
    batter_name = (await context.bot.get_chat(game["current_players"]["batter"])).first_name
    bowler_name = (await context.bot.get_chat(game["current_players"]["bowler"])).first_name

    # Notify players of wicket
    for player_id in [game["player1"], game["player2"]]:
        await context.bot.edit_message_text(
            chat_id=player_id,
            message_id=game["message_id"][player_id],
            text=f"🎯 WICKET! {batter_name} out!\n"
                 f"{bowler_name} bowled {game['bowler_choice']}\n"
                 f"Innings Over!",
            parse_mode="Markdown"
        )

    await end_innings(game_code, context)

async def end_innings(game_code: str, context: CallbackContext):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    if game["innings"] == 1:
        # Switch to second innings with proper reset
        game["innings"] = 2
        game["target"] = game["score1"] + 1
        game["current_players"] = {
            "batter": game["player2"],
            "bowler": game["player1"]
        }
        game["batter"] = game["player2"]
        game["bowler"] = game["player1"]
        # Reset counters for new innings
        game["wickets"] = 0
        game["over"] = 0
        game["ball"] = 0
        game["score2"] = 0  # Reset second innings score
    else:
        # Both innings completed
        await declare_winner(game_code, context)
    await update_game_interface(game_code, context)

async def chat_message(update: Update, context: CallbackContext) -> None:
    if update.message is None:
        return

    user_id = update.effective_user.id
    message = update.message

    # Ignore commands
    if message.text and message.text.startswith('/'):
        return

    # Forward messages only in private chats
    if update.message.chat.type != "private":
        return

    # Find active game for this user
    for game_code in list(cricket_games.keys()):
        game = cricket_games.get(game_code)
        if not game:
            continue

        if user_id not in [game["player1"], game["player2"]]:
            continue

        other_player_id = game["player2"] if user_id == game["player1"] else game["player1"]
        sender_name = update.effective_user.first_name

        try:
            if message.text:
                await context.bot.send_message(
                    chat_id=other_player_id,
                    text=f"{message.text}"
                )
            elif message.sticker:
                # Forward the sticker directly without any additional text
                await context.bot.send_sticker(
                    chat_id=other_player_id,
                    sticker=message.sticker.file_id
                )
        except Exception as e:
            print(f"Error forwarding message: {e}")
            break

async def declare_winner(game_code: str, context: CallbackContext):
    game = cricket_games[game_code]
    p1 = (await context.bot.get_chat(game["player1"])).first_name
    p2 = (await context.bot.get_chat(game["player2"])).first_name

    # Determine match outcome
    if game["innings"] == 2:
        # Second innings completed
        if game["score2"] >= game["target"]:
            result = f"🏅 {p2} won by chasing the target!"
        else:
            runs_diff = game["target"] - game["score2"] - 1
            result = f"🏅 {p1} won by {runs_diff} runs!"
    else:
        # Single innings comparison
        if game["score1"] > game["score2"]:
            runs_diff = game["score1"] - game["score2"]
            result = f"🏅 {p1} won by {runs_diff} runs!"
        elif game["score1"] < game["score2"]:
            runs_diff = game["score2"] - game["score1"]
            result = f"🏅 {p2} won by {runs_diff} runs!"
        else:
            result = "🤝 It's a draw!"

    # Build result message
    result_text = (
        f"🏆 *MATCH RESULT*\n\n"
        f"🧑 {p1}: {game['score1']} runs\n"
        f"🧑 {p2}: {game['score2']} runs\n\n"
        f"{result}"
    )

    # Notify all participants
    all_players = [game["player1"], game["player2"]] + list(game["spectators"])
    for player_id in all_players:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=result_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error sending result: {e}")

    del cricket_games[game_code]
