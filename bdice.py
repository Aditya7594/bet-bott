from telegram import Update
from telegram.ext import CallbackContext
import random
from pymongo import MongoClient
import asyncio  # For introducing delay between animations

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

    if user_guess < 3 or user_guess > 18:
        await update.message.reply_text("Your guess must be between 3 and 18.")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to use /start first to register.")
        return

    if user_data['credits'] < bet_amount:
        await update.message.reply_text("You don't have enough credits for this bet.")
        return

    # Send dice animation and collect results
    dice_results = []
    for i in range(3):
        dice_message = await update.message.reply_dice(emoji="🎲")  # Send animated dice
        await asyncio.sleep(3)  # Wait for the animation to finish
        dice_results.append(dice_message.dice.value)

    # Calculate total dice result
    dice_total = sum(dice_results)

    # Calculate reward multiplier
    difference = abs(user_guess - dice_total)
    if difference == 0:
        multiplier = 5
    elif difference <= 1:
        multiplier = 3
    elif difference <= 3:
        multiplier = 1.5
    elif difference <= 6:
        multiplier = 0.5
    else:
        multiplier = 0

    winnings = int(bet_amount * multiplier)
    user_data['credits'] += winnings - bet_amount
    save_user(user_data)

    # Send results
    await update.message.reply_text(
        f"🎲 *Rolling Dice...*\n"
        f"🎲 Dice Results: {dice_results[0]}, {dice_results[1]}, {dice_results[2]} (Total: {dice_total})\n"
        f"Your Guess: {user_guess}\n"
        f"🎉 You won {winnings} credits!\n💰 New Balance: {user_data['credits']} credits.",
        parse_mode="Markdown"
    )
