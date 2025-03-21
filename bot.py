from pymongo import MongoClient
import asyncio
import os
import secrets
from flask import Flask
from threading import Thread
import requests
import logging
from telegram import Update, ChatPermissions
from telegram.ext import filters, ContextTypes
from functools import wraps
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, filters
from token_1 import token


from genshin_game import pull, bag, reward_primos, add_primos, leaderboard, handle_message, button, reset_bag_data, drop_primos, set_threshold, handle_artifact_button,send_artifact_reward
from cricket import chat_cricket, join_cricket, toss_button, choose_button, play_button, update_game_interface, handle_wicket, end_innings, declare_winner
from minigame import dart, basketball, flip, dice, credits_leaderboard,football
from bdice import bdice
from claim import daily, random_claim, claim_credits, send_random_claim
from bank import exchange, sell, store, withdraw, bank
from hilo_game import start_hilo, hilo_click, hilo_cashout
from cards import gacha, gacha, my_collection,view_card, card_pull
from mines_game import Mines, Mines_click, Mines_CashOut
OWNER_ID = 5667016949
muted_users = set()
last_interaction_time = {}
user_daily_credits = {}


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
users_collection = db['users']
genshin_collection = db['genshin_users']

# MongoDB management functions
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def get_genshin_user_by_id(user_id):
    return genshin_collection.find_one({"user_id": user_id})

def save_genshin_user(user_data):
    genshin_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def escape_markdown_v2(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

def generate_referral_link(user_id):
    return f"https://t.me/YourBotUsername?start=ref{user_id}"



def check_started(func):
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        if get_user_by_id(user_id) is None:
            await update.message.reply_text("You need to start the bot first by using /start.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    first_name = user.first_name

    if context.args and context.args[0].startswith("ref"):
        referrer_id = str(context.args[0][3:])
        referrer = get_user_by_id(referrer_id)

        if referrer and referrer_id != user_id:
            logging.info(f"Referrer before update: {referrer}")
            existing_user = get_user_by_id(user_id)
            if not existing_user:
                referrer['credits'] = referrer.get('credits', 0) + 1000
                referrer['primos'] = referrer.get('primos', 0) + 1000
                referrer['referrals'] = referrer.get('referrals', 0) + 1
                save_user(referrer)

                logging.info(f"Referrer after update: {referrer}")

                await context.bot.send_message(
                    referrer_id,
                    f"🎉 You referred {first_name} to the bot and earned 1,000 credits"
                )

    existing_user = get_user_by_id(user_id)
    if not existing_user:
        new_user = {
            "user_id": user_id,
            "first_name": first_name,
            "join_date": datetime.now().strftime('%m/%d/%y'),
            "credits": 5000 + (1000 if context.args and context.args[0].startswith("ref") else 0),
            "primos": 1000 if context.args and context.args[0].startswith("ref") else 0,
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "bag": {},
            "referrals": 0
        }
        save_user(new_user)

        logging.info(f"New user created: {new_user}")

        await update.message.reply_text(
            f"Welcome {first_name}! You've received 5,000 credits and 16,000 Primogems to start betting. Use /profile to check your details."
        )

        if context.args and context.args[0].startswith("ref"):
            await update.message.reply_text(
                "🎉 You joined through a referral link and earned 1,000 credits!"
            )
    else:
        await update.message.reply_text(
            f"Welcome back, {first_name}! Use /profile to view your details."
        )

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Shadow'

def run_flask():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_flask).start()

async def keep_alive(context: CallbackContext):
    channel_id = -1002192932215 
    try:
        requests.get("https://your-app-name.herokuapp.com/")  # Replace with your URL
        await context.bot.send_message(chat_id=channel_id, text="🤖 Bot is alive and running!")
    except Exception as e:
        logger.error(f"Failed to send keep-alive message: {e}")


async def reffer(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Fetch user data from the database to check how many users they've referred
    user_data = get_user_by_id(user_id)

    if user_data:
        referral_count = user_data.get('referrals', 0)
    else:
        referral_count = 0

    # Generate a referral link
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref{user_id}"

    # Send the referral link and the referral count to the user
    await update.message.reply_text(
        f"🔗 Share this referral link with your friends:\n\n"
        f"{referral_link}\n\n"
        f"You have referred {referral_count} users.\n\n"
        "When they join and start the bot using your link, both of you will receive 1000 credits and 1000 Primogems!"
    )



async def profile(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Fetch user data from the database
    user_data = get_user_by_id(user_id)

    if user_data:
        # Get the number of gold, silver, and bronze coins in the user's bag
        gold_coins = user_data['bag'].get('gold', 0)
        silver_coins = user_data['bag'].get('silver', 0)
        bronze_coins = user_data['bag'].get('bronze', 0)

        # Construct the profile message with clear boundaries and formatting
        profile_message = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: {user.first_name}\n"
            f"🆔 ID: {user_data['user_id']}\n"
            f"💰 Credits: {user_data['credits']} 💎\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 Wins: {user_data['win']}\n"
            f"💔 Losses: {user_data['loss']}\n"
            f"🎖️ Title: {user_data['title']}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 Gold Coins: {gold_coins}\n"
            f"🥈 Silver Coins: {silver_coins}\n"
            f"🥉 Bronze Coins: {bronze_coins}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Send profile message with photo if available
        try:
            photos = await context.bot.get_user_profile_photos(user_id)
            if photos.photos:
                # Use the smallest size available (last element in the list)
                smallest_photo = photos.photos[0][-1].file_id
                await update.message.reply_photo(photo=smallest_photo, caption=profile_message)
            else:
                await update.message.reply_text(profile_message)
        except Exception as e:
            logger.error(f"Error fetching user photo: {e}")
            await update.message.reply_text(profile_message)
    else:
        await update.message.reply_text("You need to start the bot first by using /start.")


async def add_credits(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    target_user_id = None
    credits_to_add = None

    # Check if the user is the owner
    if user_id != OWNER_ID:  # Ensure OWNER_ID is a single integer
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Parse command arguments
    try:
        target_user_id = int(context.args[0])  # User ID of the target user
        credits_to_add = int(context.args[1])  # Amount of credits to add
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addcredits <user_id> <credits_amount>")
        return

    # Fetch the user's data from the database
    target_user_data = get_user_by_id(str(target_user_id))
    if target_user_data is None:
        await update.message.reply_text("User not found.")
        return

    # Add the credits to the target user
    new_credits = target_user_data.get('credits', 0) + credits_to_add  # Handle missing 'credits' key
    target_user_data['credits'] = new_credits
    save_user(target_user_data)

    # Send confirmation message
    await update.message.reply_text(f"Successfully added {credits_to_add} credits to user {target_user_id}. New balance: {new_credits} credits.")


async def check_game_timeout():
    current_time = datetime.now()
    
    for user_id, last_time in last_interaction_time.items():
        if (current_time - last_time).total_seconds() > 180:  # If no interaction for 3 minutes
            game_state = cd.get(user_id)
            if game_state:
                # Refund the credits and remove the game data
                bet = game_state['bet']
                user_data = get_user_by_id(user_id)
                if user_data:
                    user_data['credits'] += bet
                    save_user(user_data)
                
                # Notify user and delete game data
                await context.bot.send_message(user_id, "Your game was canceled due to inactivity. Your credits have been refunded.")
                del cd[user_id]  # Remove the game state

            # Remove from the timeout tracker
            del last_interaction_time[user_id]

async def timeout_task():
    while True:
        await asyncio.sleep(60)  # Wait for 1 minute
        await check_game_timeout()


async def reset(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Create inline keyboard for confirmation
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data="reset_yes"),
            InlineKeyboardButton("No", callback_data="reset_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Are you sure you want to reset all user data? This will wipe all progress!",
        reply_markup=reply_markup
    )

async def reset_confirmation(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await query.answer("You don't have permission to do this.", show_alert=True)
        return

    # Check the callback data (Yes or No)
    if query.data == "reset_yes":
        # Reset all users' data and set specified values to defaults
        users_collection.update_many({}, {"$set": {
            "credits": 5000,  # Set credits to 5000 after reset
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "primos": 0,
            "bag": {},
            "bank": 0,  # Reset bank balance to 0
            "gold_coins": 0,  # Reset gold coins to 0
            "silver_coins": 0,  # Reset silver coins to 0
            "bronze_coins": 0,  # Reset bronze coins to 0
            "cards": [],  # Reset cards to 0
        }})
        
        # Inform the owner that the reset was successful
        await query.answer("All user data has been reset to default values, and all users have received 5000 credits.", show_alert=True)

    elif query.data == "reset_no":
        # Inform the owner that the reset was canceled
        await query.answer("User data reset was canceled.", show_alert=True)

    # Delete the inline keyboard after answering
    await query.edit_message_reply_markup(reply_markup=None)

async def reach(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await update.message.reply_text("🔒 You don't have permission to use this command.")
        return

    try:
        # Fetch total users
        total_users = users_collection.count_documents({})

        # Fetch total Genshin users
        total_genshin_users = genshin_collection.count_documents({})

        # Fetch total credits in the game
        total_credits_result = users_collection.aggregate([
            {"$group": {"_id": None, "total_credits": {"$sum": "$credits"}}}
        ])
        total_credits_value = next(total_credits_result, {}).get("total_credits", 0)

        # Fetch total groups the bot is in
        total_groups = db["groups"].count_documents({})  # Assuming you have a 'groups' collection

        # Construct the stats message
        stats_message = (
            "<b>🤖 Bot Statistics:</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🌌 Total Genshin Users: {total_genshin_users}\n"
            f"💰 Total Credits in Game: {total_credits_value}\n"
            f"🏢 Total Groups: {total_groups}\n"
        )

        await update.message.reply_text(stats_message, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in /reach command: {e}")
        await update.message.reply_text("An error occurred while fetching bot stats. Please try again later.")

async def broadcast(update: Update, context: CallbackContext) -> None:
    # Check if the user is the owner
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🔒 You don't have permission to use this command.")
        return

    # Check if a message is provided
    if not context.args:
        await update.message.reply_text("❗ Usage: /broadcast <message>")
        return

    # Combine the arguments into a single message
    broadcast_message = " ".join(context.args)

    # Fetch all users and groups from the database
    users = users_collection.find({}, {"user_id": 1})
    groups = []  

    # Counters for tracking
    successful_users = 0
    failed_users = 0
    successful_groups = 0
    failed_groups = 0

    # Send the message to all users
    for user in users:
        user_id = user["user_id"]
        try:
            await context.bot.send_message(chat_id=user_id, text=broadcast_message)
            successful_users += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            failed_users += 1

    # Send the message to all groups (if applicable)
    for group in groups:
        group_id = group["group_id"]
        try:
            await context.bot.send_message(chat_id=group_id, text=broadcast_message)
            successful_groups += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to group {group_id}: {e}")
            failed_groups += 1

    # Send a report to the owner
    report_message = (
        "📢 **Broadcast Report**\n\n"
        f"✅ Successfully sent to {successful_users} users and {successful_groups} groups.\n"
        f"❌ Failed to send to {failed_users} users and {failed_groups} groups.\n\n"
        f"Total recipients: {successful_users + successful_groups}\n"
        f"Total failures: {failed_users + failed_groups}"
    )

    await update.message.reply_text(report_message)

async def give(update: Update, context: CallbackContext) -> None:
    giver = update.effective_user
    giver_id = str(giver.id)
    message = update.message

    # Check if the command is a reply or has a tagged user
    if message.reply_to_message:
        receiver = message.reply_to_message.from_user
    elif message.entities and len(message.entities) > 1:
        receiver = message.parse_entities().get(list(message.entities)[1])
    else:
        await update.message.reply_text("Please tag a user or reply to their message to give credits.")
        return

    receiver_id = str(receiver.id)

    # Ensure the giver and receiver are not the same
    if giver_id == receiver_id:
        await update.message.reply_text("You cannot give credits to yourself.")
        return

    # Check if an amount was provided
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /give <amount> (by tagging or replying to a user).")
        return

    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("Please specify a positive amount of credits to give.")
        return

    # Fetch data for both users
    giver_data = get_user_by_id(giver_id)
    receiver_data = get_user_by_id(receiver_id)

    if not giver_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return
    if not receiver_data:
        await update.message.reply_text("The user you are trying to give credits to hasn't started the bot.")
        return

    # Check if the giver has enough credits
    if giver_data['credits'] < amount:
        await update.message.reply_text(f"You don't have enough credits to give. Your current balance is {giver_data['credits']}.")
        return

    # Update the balances
    giver_data['credits'] -= amount
    receiver_data['credits'] += amount

    save_user(giver_data)
    save_user(receiver_data)

    # Notify both users
    await update.message.reply_text(
        f"Successfully transferred {amount} credits to {receiver.first_name}. Your new balance is {giver_data['credits']} credits."
    )
    await context.bot.send_message(
        chat_id=receiver_id,
        text=f"You have received {amount} credits from {giver.first_name}! Your new balance is {receiver_data['credits']} credits."
    )


def main() -> None:
    application = Application.builder().token(token).build()

    # Add all handlers inside the main function
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", check_started(profile)))
    application.add_handler(CommandHandler("flip", check_started(flip)))
    application.add_handler(CommandHandler("dart", check_started(dart)))
    application.add_handler(CommandHandler("basketball", check_started(basketball)))
    application.add_handler(CommandHandler("football", check_started(football)))
    application.add_handler(CommandHandler("dice", check_started(dice)))
    application.add_handler(CommandHandler("pull", check_started(pull)))  # Pull command
    application.add_handler(CommandHandler("bag", check_started(bag)))  # Bag command
    application.add_handler(CommandHandler('add_primos', check_started(add_primos)))  # Add primos (admin)
    application.add_handler(CommandHandler("Primos_leaderboard", check_started(leaderboard)))  # Primos leaderboard
    application.add_handler(CommandHandler('drop_primos', check_started(drop_primos)))  # Drop primos (admin)
    application.add_handler(CommandHandler("addcredits", check_started(add_credits)))
    application.add_handler(CommandHandler("reset_bag_data", check_started(reset_bag_data)))  # Reset bag data (admin)
    application.add_handler(CommandHandler("leaderboard", check_started(credits_leaderboard)))
    application.add_handler(CommandHandler("exchange", check_started(exchange)))  
    application.add_handler(CommandHandler("sell", check_started(sell)))  
    application.add_handler(CommandHandler("store", check_started(store)))  
    application.add_handler(CommandHandler("withdraw", check_started(withdraw))) 
    application.add_handler(CommandHandler("bank", bank))
    application.add_handler(CommandHandler("reach", reach))
    application.add_handler(CommandHandler("reffer", reffer))

    application.add_handler(CommandHandler("bdice", check_started(bdice)))

    application.add_handler(CommandHandler("daily", check_started(daily)))
    application.add_handler(CallbackQueryHandler(claim_credits, pattern="^claim_"))
    application.add_handler(CallbackQueryHandler(random_claim, pattern="^random_claim$"))

    application.add_handler(CommandHandler("hilo", start_hilo))
    application.add_handler(CallbackQueryHandler(hilo_click, pattern="hilo_(high|low)"))
    application.add_handler(CallbackQueryHandler(hilo_cashout, pattern="hilo_cashout"))

    application.add_handler(CommandHandler("give", check_started(give)))

    application.add_handler(CommandHandler("gacha", gacha))
    application.add_handler(CommandHandler("mycollection", my_collection))
    application.add_handler(CommandHandler("view", view_card))
    application.add_handler(CallbackQueryHandler(card_pull, pattern="^(normal|special)$"))

    application.add_handler(CommandHandler("reset", reset))  
    application.add_handler(CallbackQueryHandler(reset_confirmation, pattern="^reset_"))  

  
    application.add_handler(CommandHandler("set", set_threshold)) 
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_artifact_button, pattern="^artifact_")) 
    
    application.add_handler(CommandHandler("broadcast", broadcast))
    
    application.add_handler(CommandHandler("chatcricket", chat_cricket))
    application.add_handler(CommandHandler("join", join_cricket))
    application.add_handler(CallbackQueryHandler(toss_button, pattern="^toss_"))
    application.add_handler(CallbackQueryHandler(choose_button, pattern="^choose_"))
    application.add_handler(CallbackQueryHandler(play_button, pattern="^play_"))

    application.add_handler(CommandHandler("Mines", check_started(Mines)))  # Mines command
    application.add_handler(CallbackQueryHandler(Mines_click, pattern="^[0-9]+$"))  # Tile clicks
    application.add_handler(CallbackQueryHandler(Mines_CashOut, pattern="^MinesCashOut$"))

    application.job_queue.run_repeating(keep_alive, interval=600, first=0)


    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reward_primos))  
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


    application.job_queue.run_once(timeout_task, 0)

  
    application.add_handler(CallbackQueryHandler(button))

    # Run the bot
    application.run_polling()


if __name__ == '__main__':
    main()
