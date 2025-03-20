import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext

cricket_games = {}

def generate_game_code():
    return str(random.randint(100, 999))

async def chat_cricket(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    game_code = generate_game_code()
    while game_code in cricket_games:
        game_code = generate_game_code()

    cricket_games[game_code] = {
        "player1": user_id,
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
        "target": None  # Target score for the second innings
    }

    await context.bot.send_message(
        chat_id=user_id,
        text=f"🎮 *Game Started!*\nCode: `{game_code}`",
        parse_mode="Markdown"
    )

async def join_cricket(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    game_code = context.args[0] if context.args else None

    if not game_code or game_code not in cricket_games:
        await update.message.reply_text("Invalid code!")
        return

    game = cricket_games[game_code]
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

async def declare_winner(game_code: str, context: CallbackContext):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    p1 = (await context.bot.get_chat(game["player1"])).first_name
    p2 = (await context.bot.get_chat(game["player2"])).first_name

    result = f"🏆 GAME OVER!\n{p1}: {game['score1']}\n{p2}: {game['score2']}\n"
    if game["innings"] == 2:
        if game["score2"] >= game["target"]:
            result += f"🏅 Winner: {p2} (Chased {game['target']})"
        else:
            result += f"🏅 Winner: {p1} (Defended {game['target'] - 1})"
    else:
        result += f"🏅 Winner: {p1 if game['score1'] > game['score2'] else p2}" if game['score1'] != game['score2'] else "Tie!"

    for player_id in [game["player1"], game["player2"]]:
        await context.bot.edit_message_text(
            chat_id=player_id,
            message_id=game["message_id"][player_id],
            text=result,
            parse_mode="Markdown"
        )
    del cricket_games[game_code]

