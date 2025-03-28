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
    
    # Only allow creating games in group chats
    if update.effective_chat.type == "private":
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ This command can only be used in group chats!")
        return
    
    user_data = user_collection.find_one({"user_id": str(user.id)})
    if not user_data:
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("Start Bot", url=f"https://t.me/{bot_username}?start=start")]]
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ You need to start the bot first to create a match!",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return

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
        "match_details": [],
        "wickets": 0,
        "max_wickets": 1,
        "max_overs": 20,
        "spectators": set(),
    }

    # Create callback buttons instead of URL buttons
    join_button = InlineKeyboardButton("Join Game", callback_data=f"join_{game_code}")
    watch_button = InlineKeyboardButton("Watch Game", callback_data=f"watch_{game_code}")
    keyboard = InlineKeyboardMarkup([[join_button], [watch_button]])

    try:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎮 *Game Started!*\nCode: `{game_code}`\n\n"
                 f"To join, click the button or send /join {game_code}\n"
                 f"To watch, click Watch Game or send /watch {game_code}",
            reply_markup=keyboard,
            parse_mode="Markdown")
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.message_id)
    except Exception as e:
        print(f"Error creating game: {e}")

async def update_game_interface(game_code: str, context: CallbackContext, text: str = None):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    if not text:
        batter_name = (await context.bot.get_chat(game["batter"])).first_name
        bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
        score = game['score1'] if game['innings'] == 1 else game['score2']
        target = game['target'] if game['innings'] == 2 else None
        spectator_count = len(game["spectators"])
        
        # Put spectator count in the top right, separate from overs
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

    # Create the keyboard with buttons
    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])

    # Update message for all participants
    recipients = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in recipients:
        try:
            # If no message ID exists for this player, send a new message and pin it
            if player_id not in game["message_id"]:
                msg = await context.bot.send_message(
                    chat_id=player_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard) if player_id not in game["spectators"] else None,
                    parse_mode="Markdown"
                )
                game["message_id"][player_id] = msg.message_id
                
                # Try to pin the message in DM
                try:
                    await context.bot.pin_chat_message(
                        chat_id=player_id,
                        message_id=msg.message_id,
                        disable_notification=True
                    )
                except Exception as e:
                    print(f"Couldn't pin message: {e}")
            else:
                # Update existing message
                await context.bot.edit_message_text(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id),
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard) if player_id not in game["spectators"] else None,
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"Error updating game interface for {player_id}: {e}")

async def handle_join_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_code = query.data.split('_')

    if game_code not in cricket_games:
        await query.answer("Game not found or expired!")
        return

    game = cricket_games[game_code]
    
    if user_id == game["player1"]:
        await query.answer("You can't join your own game!")
        return

    if game["player2"]:
        await query.answer("Game full!")
        return

    game["player2"] = user_id
    await context.bot.send_message(
        chat_id=game["group_chat_id"],
        text=f"🎉 {query.from_user.first_name} joined the game!")

    keyboard = [[
        InlineKeyboardButton("Heads", callback_data=f"toss_{game_code}_heads"),
        InlineKeyboardButton("Tails", callback_data=f"toss_{game_code}_tails")
    ]]
    
    for player_id in [game["player1"], game["player2"]]:
        try:
            msg = await context.bot.send_message(
                chat_id=player_id,
                text="⚡ Toss Time!",
                reply_markup=InlineKeyboardMarkup(keyboard))
            game["message_id"][player_id] = msg.message_id
        except Exception as e:
            print(f"Error sending toss: {e}")

async def handle_watch_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_code = query.data.split('_')

    if game_code not in cricket_games:
        await query.answer("Game not found or expired!")
        return

    game = cricket_games[game_code]
    
    # Check if user is already a player
    if user_id in [game["player1"], game["player2"]]:
        await query.answer("You're already playing in this game!")
        return
    
    # Add user to spectators
    game["spectators"].add(user_id)
    
    player1_name = (await context.bot.get_chat(game["player1"])).first_name
    player2_name = "Waiting for opponent" if not game["player2"] else (await context.bot.get_chat(game["player2"])).first_name
    
    await query.message.reply_text(
        f"🎮 You're now watching match: {game_code}\n"
        f"🧑 Player 1: {player1_name}\n"
        f"🧑 Player 2: {player2_name}\n\n"
        f"Match updates will appear shortly!"
    )
    
    # If game is already in progress, update the interface for the spectator
    if game["player2"] and "batter" in game and game["batter"]:
        await update_game_interface(game_code, context)

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
                    row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
                    if len(row) == 3:
                        keyboard.append(row)
                        row = []
                keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{game_code}")])
            
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
        await query.answer(f"Your choice: {number}")
        
        # Process the result now that both players have chosen
        batter_choice = game["batter_choice"]
        bowler_choice = number
        
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
            await handle_wicket(game_code, context)
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
                
                await declare_winner(game_code, context)
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
                
                await end_innings(game_code, context)
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
            row.append(InlineKeyboardButton(str(i), callback_data=f"play_{game_code}_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        
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
        await query.answer("Not your turn!")
        return

async def declare_winner(game_code: str, context: CallbackContext):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    p1 = (await context.bot.get_chat(game["player1"])).first_name
    p2 = (await context.bot.get_chat(game["player2"])).first_name

    # Determine the result
    if game["score1"] == game["score2"]:
        result = "🤝 Match Drawn!"
    elif game["innings"] == 2:
        if game["score2"] >= game["target"]:
            winner = (await context.bot.get_chat(game["batter"])).first_name
            loser = (await context.bot.get_chat(game["bowler"])).first_name
            result = f"🏅 {winner} won by {game['max_wickets'] - game['wickets']} wicket(s)!"
        else:
            winner = (await context.bot.get_chat(game["bowler"])).first_name
            diff = game["target"] - game["score2"] - 1
            result = f"🏅 {winner} won by {diff} runs!"
    else:
        # This shouldn't normally happen as we should always end with innings 2
        result = "Match ended unexpectedly!"

    # Build the result message
    result_message = (
        f"🏆 *GAME OVER!*\n\n"
        f"📜 *Match Summary:*\n"
        f"🧑 {p1}: {game['score1']} runs\n"
        f"🧑 {p2}: {game['score2']} runs\n\n"
        f"{result}"
    )

    # Send the result to the group chat where the game was started
    try:
        await context.bot.send_message(
            chat_id=game["group_chat_id"],
            text=result_message,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error sending result to group chat: {e}")

    # Notify players and spectators
    participants = list(game["spectators"]) + [game["player1"], game["player2"]]
    for player_id in participants:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=result_message,
                parse_mode="Markdown"
            )
            
            # Try to unpin the game message
            try:
                await context.bot.unpin_chat_message(
                    chat_id=player_id,
                    message_id=game["message_id"].get(player_id)
                )
            except Exception as e:
                print(f"Error unpinning message for {player_id}: {e}")
                
        except Exception as e:
            print(f"Error sending result to {player_id}: {e}")

    # Remove the game from active games
    del cricket_games[game_code]

async def handle_wicket(game_code: str, context: CallbackContext):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    
    # Update ball counter
    game["ball"] += 1
    if game["ball"] == 6:
        game["over"] += 1
        game["ball"] = 0

    # Check if we need to end the innings
    if game["wickets"] >= game["max_wickets"] or game["over"] >= game["max_overs"]:
        await end_innings(game_code, context)
        return
    
    # Continue the current innings
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
    
    text += "\n\n⚡ Next ball. Batter, choose a number (1-6):"
    
    await update_game_interface(game_code, context, text)

async def end_innings(game_code: str, context: CallbackContext):
    if game_code not in cricket_games:
        return

    game = cricket_games[game_code]
    
    if game["innings"] == 1:
        # Switch to second innings
        game["innings"] = 2
        game["target"] = game["score1"] + 1
        
        # Swap batting and bowling roles
        game["batter"], game["bowler"] = game["bowler"], game["batter"]
        game["current_players"] = {
            "batter": game["batter"],
            "bowler": game["bowler"]
        }
        
        # Reset counters
        game["wickets"] = 0
        game["over"] = 0
        game["ball"] = 0
        game["score2"] = 0
        
        # Build innings break message
        batter_name = (await context.bot.get_chat(game["batter"])).first_name
        bowler_name = (await context.bot.get_chat(game["bowler"])).first_name
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
        
        # Reset choices for new innings
        game["batter_choice"] = None
        game["bowler_choice"] = None
        
        # Update the game interface with innings break info
        await update_game_interface(game_code, context, text)
    else:
        # Game over - declare winner
        await declare_winner(game_code, context)

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

        # Check if the user is part of this game (player or spectator)
        if user_id not in [game["player1"], game["player2"]] and user_id not in game["spectators"]:
            continue

        # Get all participants (players and spectators)
        participants = list(game["spectators"]) + [game["player1"], game["player2"]]
        
        # Forward message to all other participants
        for participant_id in participants:
            if participant_id != user_id:  # Don't forward to sender
                try:
                    if message.text:
                        await context.bot.send_message(
                            chat_id=participant_id,
                            text=f"💬 {update.effective_user.first_name}: {message.text}"
                        )
                    elif message.sticker:
                        await context.bot.send_sticker(
                            chat_id=participant_id,
                            sticker=message.sticker.file_id
                        )
                except Exception as e:
                    print(f"Error forwarding message: {e}")
                    continue
        break  # Found and processed the game, no need to check others

def get_cricket_handlers():
    """Return all cricket game handlers."""
    return [
        CallbackQueryHandler(toss_button, pattern="^toss_"),
        CallbackQueryHandler(choose_button, pattern="^choose_"),
        CallbackQueryHandler(play_button, pattern="^play_"),
        CallbackQueryHandler(handle_join_button, pattern="^join_"),
        CallbackQueryHandler(handle_watch_button, pattern="^watch_")
    ]
