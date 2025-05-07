from flask import Flask
from threading import Thread

# Create Flask app
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Shadow'

# Function to run Flask
def run_flask():
    app.run(host="0.0.0.0", port=8000)

# Start Flask server in background thread
flask_thread = Thread(target=run_flask)
flask_thread.start()

# After this, you start your Telegram bot normally
# Example:
# from your_bot import application
# application.run_polling()

