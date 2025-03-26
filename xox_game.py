from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient
import uuid
from datetime import datetime, timedelta

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
games_collection = db['xox_games']
stats_collection = db['xox_stats']

def check_winner(board):
    for row in board:
        if row.count(row[0]) == 3 and row[0] != "":
            return True
    for col in range(3):
        if board[0][col] == board[1][col] == board[2][col] and board[0][col] != "":
            return True
    if board[0][0] == board[1][1] == board[2][2] and board[0][0] != "":
        return True
    if board[0][2] == board[1][1] == board[2][0] and board[0][2] != "":
        return True
    return False

def generate_board_buttons(board, game_id):
    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            cell = board[i][j]
            text = cell if cell else "⬜"
            row.append(InlineKeyboardButton(text, callback_data=f"{game_id}:{i}_{j}"))
        keyboard.append(row)
    # Add forfeit button
    keyboard.append([InlineKeyboardButton("🏳️ Forfeit", callback_data=f"{game_id}:forfeit")])
    return InlineKeyboardMarkup(keyboard)

def update_stats(winner_id, loser_id):
    # Update winner stats
    stats_collection.update_one(
        {"user_id": winner_id},
        {
            "$inc": {"wins": 1, "games_played": 1},
            "$setOnInsert": {"losses": 0, "draws": 0}
        },
        upsert=True
    )
    # Update loser stats
    stats_collection.update_one(
        {"user_id": loser_id},
        {
            "$inc": {"losses": 1, "games_played": 1},
            "$setOnInsert": {"wins": 0, "draws": 0}
        },
        upsert=True
    )

async def xox(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    game_id = str(uuid.uuid4())
    
    # Check if user has an active game
    active_game = games_collection.find_one({
        "$or": [{"player1": user_id}, {"player2": user_id}],
        "active": True
    })
    if active_game:
        await update.message.reply_text(
            "❌ You already have an active game! Please finish or forfeit it first.",
            parse_mode="HTML"
        )
        return

    new_game = {
        "_id": game_id,
        "player1": user_id,
        "player2": None,
        "turn": user_id,
        "board": [["", "", ""] for _ in range(3)],
        "active": True,
        "created_at": datetime.utcnow(),
        "last_move": datetime.utcnow()
    }
    games_collection.insert_one(new_game)
    
    await update.message.reply_text(
        "🎮 *Tic-Tac-Toe (XOX) Game Started!* 🎮\n\n"
        f"Player 1: {user.mention_html()} ❌\n"
        "Waiting for Player 2 to join! Click any cell to join the game.\n\n"
        "Game will timeout after 5 minutes of inactivity.",
        reply_markup=generate_board_buttons(new_game["board"], game_id),
        parse_mode="HTML"
    )

async def handle_xox_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = update.effective_user
    user_id = str(user.id)
    await query.answer()
    
    try:
        game_id, action = query.data.split(":")
        if action == "forfeit":
            await handle_forfeit(query, game_id, user_id)
            return
        row, col = map(int, action.split("_"))
    except ValueError:
        await query.answer("Invalid move data!")
        return

    game = games_collection.find_one({"_id": game_id, "active": True})
    if not game:
        await query.edit_message_text("This game is no longer active or doesn't exist.")
        return

    # Check for game timeout (5 minutes)
    if (datetime.utcnow() - game["last_move"]) > timedelta(minutes=5):
        await handle_timeout(query, game)
        return

    if game["player2"] is None and user_id != game["player1"]:
        game["player2"] = user_id
        games_collection.update_one(
            {"_id": game_id},
            {
                "$set": {
                    "player2": user_id,
                    "last_move": datetime.utcnow()
                }
            }
        )
        await query.edit_message_text(
            f"🎮 *Tic-Tac-Toe (XOX) Game Started!* 🎮\n\n"
            f"Player 1: {query.message.reply_to_message.from_user.mention_html()} ❌\n"
            f"Player 2: {user.mention_html()} ⭕\n\n"
            f"Current turn: {query.message.reply_to_message.from_user.mention_html()}",
            reply_markup=generate_board_buttons(game["board"], game_id),
            parse_mode="HTML"
        )
        return

    if user_id not in [game["player1"], game["player2"]]:
        await query.answer("You're not part of this game!")
        return

    if game["turn"] != user_id:
        await query.answer("It's not your turn!")
        return

    if game["board"][row][col]:
        await query.answer("This cell is already taken!")
        return

    symbol = "❌" if user_id == game["player1"] else "⭕"
    game["board"][row][col] = symbol
    game["last_move"] = datetime.utcnow()

    if check_winner(game["board"]):
        winner = "Player 1" if user_id == game["player1"] else "Player 2"
        games_collection.update_one({"_id": game_id}, {"$set": {"active": False}})
        update_stats(user_id, game["player2"] if user_id == game["player1"] else game["player1"])
        
        await query.edit_message_text(
            f"🎉 *Game Over!* 🎉\n\n"
            f"{user.mention_html()} ({symbol}) wins! 🏆\n\n"
            f"Final Board:",
            reply_markup=generate_board_buttons(game["board"], game_id),
            parse_mode="HTML"
        )
        return

    if all(cell for row in game["board"] for cell in row):
        games_collection.update_one({"_id": game_id}, {"$set": {"active": False}})
        update_stats(game["player1"], game["player2"])
        update_stats(game["player2"], game["player1"])
        
        await query.edit_message_text(
            "🤝 *It's a Draw!* 🤝\n\n"
            f"Final Board:",
            reply_markup=generate_board_buttons(game["board"], game_id),
            parse_mode="HTML"
        )
        return

    next_turn = game["player2"] if user_id == game["player1"] else game["player1"]
    games_collection.update_one(
        {"_id": game_id},
        {
            "$set": {
                "board": game["board"],
                "turn": next_turn,
                "last_move": datetime.utcnow()
            }
        }
    )

    current_player = query.message.reply_to_message.from_user if user_id == game["player1"] else user
    await query.edit_message_text(
        f"🎮 *Tic-Tac-Toe (XOX) Game in Progress* 🎮\n\n"
        f"Player 1: {query.message.reply_to_message.from_user.mention_html()} ❌\n"
        f"Player 2: {user.mention_html()} ⭕\n\n"
        f"Current turn: {current_player.mention_html()}",
        reply_markup=generate_board_buttons(game["board"], game_id),
        parse_mode="HTML"
    )

async def handle_forfeit(query, game_id, user_id):
    game = games_collection.find_one({"_id": game_id, "active": True})
    if not game:
        await query.edit_message_text("This game is no longer active or doesn't exist.")
        return

    if user_id not in [game["player1"], game["player2"]]:
        await query.answer("You're not part of this game!")
        return

    winner_id = game["player2"] if user_id == game["player1"] else game["player1"]
    games_collection.update_one({"_id": game_id}, {"$set": {"active": False}})
    update_stats(winner_id, user_id)

    await query.edit_message_text(
        f"🏳️ *Game Forfeited!* 🏳️\n\n"
        f"{query.message.reply_to_message.from_user.mention_html()} has forfeited the game.\n"
        f"Winner: {query.message.reply_to_message.from_user.mention_html() if user_id == game['player2'] else user.mention_html()}\n\n"
        f"Final Board:",
        reply_markup=generate_board_buttons(game["board"], game_id),
        parse_mode="HTML"
    )

async def handle_timeout(query, game):
    games_collection.update_one({"_id": game["_id"]}, {"$set": {"active": False}})
    if game["player2"]:
        update_stats(game["player2"], game["player1"])
        update_stats(game["player1"], game["player2"])
    
    await query.edit_message_text(
        "⏰ *Game Timed Out!* ⏰\n\n"
        "The game has ended due to inactivity.\n"
        f"Final Board:",
        reply_markup=generate_board_buttons(game["board"], game["_id"]),
        parse_mode="HTML"
    )

async def xox_stats(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    stats = stats_collection.find_one({"user_id": user_id})
    
    if not stats:
        await update.message.reply_text(
            "📊 *Your XOX Game Statistics* 📊\n\n"
            "You haven't played any games yet!",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"📊 *Your XOX Game Statistics* 📊\n\n"
        f"Games Played: {stats.get('games_played', 0)}\n"
        f"Wins: {stats.get('wins', 0)}\n"
        f"Losses: {stats.get('losses', 0)}\n"
        f"Draws: {stats.get('draws', 0)}\n"
        f"Win Rate: {(stats.get('wins', 0) / stats.get('games_played', 1) * 100):.1f}%",
        parse_mode="HTML"
    )

def get_xox_handlers():
    return [
        CommandHandler("xox", xox),
        CommandHandler("xoxstats", xox_stats),
        CallbackQueryHandler(handle_xox_click, pattern=r"^[^:]+:[^:]+$")
    ]
