import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
from pymongo import MongoClient

# MongoDB setup
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
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("Start Bot", url=f"https://t.me/{bot_username}?start=start")]]
        await update.message.reply_text(
            "⚠️ You need to start the bot first to create a match!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    game_code = generate_game_code()
    while game_code in cricket_games:
        game_code = generate_game_code()

    try:
        # Create pinned message with proper mention
        msg = await update.message.reply_text(
            f"🏏 *New Cricket Match Started!*\n"
            f"Game Code: `{game_code}`\n"
            f"Started by: {user.mention_markdown()}\n"
            f"Use `/join {game_code}` to play!",
            parse_mode="Markdown"
        )
        await context.bot.pin_chat_message(chat_id, msg.message_id)
    except Exception as e:
        print(f"Error pinning message: {e}")
        msg = await update.message.reply_text(f"Game Code: `{game_code}`", parse_mode="Markdown")

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
        "pinned_message_id": msg.message_id,
        "status": "waiting"
    }

async def join_cricket(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    game_code = context.args[0].upper() if context.args else None

    if not game_code or game_code not in cricket_games:
        await update.message.reply_text("Invalid code!")
        return

    game = cricket_games[game_code]
    
    if user_id == game["player1"]:
        await update.message.reply_text("You can't join your own game!")
        return

    if game["player2"]:
        await update.message.reply_text("Game full!")
        return

    game["player2"] = user_id

    # Send and pin interface for both players
    for player_id in [game["player1"], game["player2"]]:
        try:
            msg = await context.bot.send_message(
                chat_id=player_id,
                text="⚡ Toss Time!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Heads", callback_data=f"toss_{game_code}_heads"),
                    InlineKeyboardButton("Tails", callback_data=f"toss_{game_code}_tails")
                ]])
            )
            game["message_id"][player_id] = msg.message_id
            await context.bot.pin_chat_message(player_id, msg.message_id)  # Pin in DM
        except Exception as e:
            print(f"Error initializing game: {e}")

async def end_innings(game_code: str, context: CallbackContext):
    game = cricket_games[game_code]
    if game["innings"] == 1:
        # Swap roles completely
        new_batter = game["player2"]
        new_bowler = game["player1"]
        
        game.update({
            "innings": 2,
            "target": game["score1"] + 1,
            "batter": new_batter,
            "bowler": new_bowler,
            "current_players": {"batter": new_batter, "bowler": new_bowler},
            "score2": 0,
            "over": 0,
            "ball": 0,
            "batter_choice": None,
            "bowler_choice": None
        })
        
        # Reset interface for both players
        await update_game_interface(game_code, context)
    else:
        await declare_winner(game_code, context)

async def declare_winner(game_code: str, context: CallbackContext):
    game = cricket_games[game_code]
    
    # Unpin messages for both players
    for player_id in [game["player1"], game["player2"]]:
        try:
            await context.bot.unpin_chat_message(player_id)
        except Exception as e:
            print(f"Error unpinning message: {e}")

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

async def update_game_interface(game_code: str, context: CallbackContext):
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

    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])

    for player_id in [game["player1"], game["player2"]]:
        try:
            await context.bot.edit_message_text(
                chat_id=player_id,
                message_id=game["message_id"][player_id],
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except:
            pass

async def play_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_code, number = query.data.split('_')
    number = int(number)

    if game_code not in cricket_games:
        await query.answer("Game expired!")
        return

    game = cricket_games[game_code]
    if user_id == game["current_players"]["batter"] and game["batter_choice"] is None:
        game["batter_choice"] = number
        await query.answer(f"You chose {number}. Waiting for bowler...")
    elif user_id == game["current_players"]["bowler"] and game["bowler_choice"] is None:
        game["bowler_choice"] = number
        await query.answer(f"You chose {number}. Processing result...")
    else:
        await query.answer("Not your turn!")
        return

    if game["batter_choice"] is not None and game["bowler_choice"] is not None:
        batter_choice = game["batter_choice"]
        bowler_choice = game["bowler_choice"]
        game["batter_choice"] = None
        game["bowler_choice"] = None

        if batter_choice == bowler_choice:
            await handle_wicket(game_code, context)
        else:
            if game["innings"] == 1:
                game["score1"] += batter_choice
            else:
                game["score2"] += batter_choice

            game["ball"] += 1
            if game["ball"] == 6:
                game["over"] += 1
                game["ball"] = 0

            # Check if target is reached in the second innings
            if game["innings"] == 2 and game["score2"] >= game["target"]:
                await declare_winner(game_code, context)
                return

    await update_game_interface(game_code, context)

async def handle_wicket(game_code: str, context: CallbackContext):
    game = cricket_games[game_code]
    batter_name = (await context.bot.get_chat(game["current_players"]["batter"])).first_name
    bowler_name = (await context.bot.get_chat(game["current_players"]["bowler"])).first_name

    # Reset over and ball count when a wicket falls
    game["over"] = 0
    game["ball"] = 0

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
        game["innings"] = 2
        game["target"] = game["score1"] + 1  # Set target for the second innings
        game["current_players"] = {"batter": game["player2"], "bowler": game["player1"]}
        game["batter"] = game["player2"]
        game["bowler"] = game["player1"]
        await update_game_interface(game_code, context)
    else:
        await declare_winner(game_code, context)


async def handle_message(update: Update, context: CallbackContext) -> None:
    if update.message.chat.type != "private":
        return

    user = update.effective_user
    message = update.message

    # Find active game for user
    active_game = None
    for code, game in cricket_games.items():
        if user.id in [game["player1"], game["player2"]] and game["status"] == "active":
            active_game = game
            break

    if not active_game:
        return

    # Forward message to opponent
    receiver_id = active_game["player2"] if user.id == active_game["player1"] else active_game["player1"]
    
    try:
        if message.text:
            await context.bot.send_message(
                chat_id=receiver_id,
                text=f"{message.text}"
            )
        elif message.sticker:
            await context.bot.send_message(
                chat_id=receiver_id,
                text=""
            )
            await context.bot.send_sticker(
                chat_id=receiver_id,
                sticker=message.sticker.file_id
            )
    except Exception as e:
        print(f"Message forwarding error: {e}")

async def declare_winner(game_code: str, context: CallbackContext):
    game = cricket_games[game_code]
    game["status"] = "ended"
    
    # Unpin original message
    try:
        await context.bot.unpin_chat_message(game["group_chat_id"], game["pinned_message_id"])
    except Exception as e:
        print(f"Error unpinning message: {e}")

    # Get player names
    p1 = await context.bot.get_chat(game["player1"])
    p2 = await context.bot.get_chat(game["player2"])

    # Build result message
    result = (
        f"🏆 *MATCH RESULTS*\n\n"
        f"👤 {p1.first_name}: {game['score1']}\n"
        f"👤 {p2.first_name}: {game['score2']}\n\n"
    )

    if game["innings"] == 2:
        if game["score2"] >= game["target"]:
            result += f"🏅 Winner: {p2.first_name} (Chased target of {game['target']})"
        else:
            result += f"🏅 Winner: {p1.first_name} (Defended target)"
    else:
        result += f"🏅 Winner: {p1.first_name if game['score1'] > game['score2'] else p2.first_name}"

    # Send to group chat
    await context.bot.send_message(
        chat_id=game["group_chat_id"],
        text=result,
        parse_mode="Markdown"
    )

    # Update player interfaces
    for player_id in [game["player1"], game["player2"]]:
        try:
            await context.bot.edit_message_text(
                chat_id=player_id,
                message_id=game["message_id"][player_id],
                text=result,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error updating player interface: {e}")

    del cricket_games[game_code]
