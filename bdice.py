from telegram import Update
from telegram.ext import CallbackContext
import random
from pymongo import MongoClient
import asyncio
from datetime import datetime  # To track the date

# Connect to MongoDB
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
users_collection = db['users']

def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

async def bdice(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    try:
        bet_amount = int(context.args[0])
        user_guess = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /bdice <bet_amount> <your_guess_total (3-18)>")
        return

    # Check if the bet amount is within the maximum limit
    max_bet = 5000
    if bet_amount > max_bet:
        await update.message.reply_text(f"The maximum bet amount is {max_bet} credits.")
        return

    if user_guess < 3 or user_guess > 18:
        await update.message.reply_text("Your guess must be between 3 and 18.")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to use /start first to register.")
        return

    # Reset bdice_daily count if the day has changed
    today = datetime.now().strftime('%Y-%m-%d')
    if 'bdice_daily' not in user_data or user_data['bdice_daily']['date'] != today:
        user_data['bdice_daily'] = {"date": today, "plays": 0}

    # Check if the user has reached their play limit
    if user_data['bdice_daily']['plays'] >= 20:
        await update.message.reply_text("You've reached your daily limit of 20 plays for /bdice.")
        return

    if user_data['credits'] < bet_amount:
        await update.message.reply_text("You don't have enough credits for this bet.")
        return

    # Increment daily play count
    user_data['bdice_daily']['plays'] += 1
    save_user(user_data)

    # Start the dice game as a background task
    asyncio.create_task(process_dice_game(update, user_data, bet_amount, user_guess))

    # Notify the user that the game is in progress
    await update.message.reply_text("Rolling the dice... Please wait for the results!")

async def process_dice_game(update: Update, user_data: dict, bet_amount: int, user_guess: int) -> None:
    # Simulate dice rolls
    dice_results = []
    for _ in range(3):
        dice_message = await update.message.reply_dice(emoji="🎲")  # Send animated dice
        await asyncio.sleep(3)  # Wait for the animation to finish
        dice_results.append(dice_message.dice.value)

    # Calculate total dice result
    dice_total = sum(dice_results)

    # Calculate reward multiplier
    difference = abs(user_guess - dice_total)
    if difference == 0:
        multiplier = 3
    elif difference <= 1:
        multiplier = 1.5
    elif difference <= 3:
        multiplier = 0.75
    else:
        multiplier = 0

    winnings = int(bet_amount * multiplier)
    user_data['credits'] += winnings - bet_amount
    save_user(user_data)

    # Send results
    await update.message.reply_text(
        f"🎲 Dice Results: *{dice_results[0]}*, *{dice_results[1]}*, *{dice_results[2]}* → Total: *{dice_total}*\n"
        f"🎯 Your Guess: *{user_guess}*\n"
        f"🏆 You {'won' if winnings > 0 else 'lost'} *{winnings} credits!*\n"
        f"💰 Balance: *{user_data['credits']} credits*\n"
        f"🎮 Plays Today: *{user_data['bdice_daily']['plays']}/20*",
        parse_mode="Markdown"
    )
