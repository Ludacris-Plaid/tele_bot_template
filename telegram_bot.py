import os
import asyncio
import requests
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8306200181:AAHP56BkD6eZOcqjI6MZNrMdU7M06S0tIrs"
BLOCKONOMICS_API_KEY = os.getenv("BLOCKONOMICS_API_KEY")

# Admin user ID (replace with actual admin user ID)
ADMIN_USER_ID = 7260656020

# Sample digital items
ITEMS = {
    "item1": {"name": "Dark Secret File", "price_btc": 0.0001, "file_path": "items/secret.pdf"},
    "item2": {"name": "Forbidden Archive", "price_btc": 0.0002, "file_path": "items/archive.zip"}
}

# Flask app for Blockonomics callback
app = Flask(__name__)

@app.route('/blockonomics/callback', methods=['POST'])
def blockonomics_callback():
    try:
        # Get the callback data
        data = request.json
        print(f"Received payment update: {data}")

        # Process payment and update records (this will be added later)
        # Here you will check for payment status, and perform actions like sending files to the user.

        # Respond with success
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500


# Admin interface
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to access this panel.")
        return

    stats = f"Total items: {len(ITEMS)}\nTotal revenue: 0 BTC"

    keyboard = [
        [InlineKeyboardButton("View Item List", callback_data="view_items")],
        [InlineKeyboardButton("Add New Item", callback_data="add_item")],
        [InlineKeyboardButton("Remove Item", callback_data="remove_item")],
        [InlineKeyboardButton("Back", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Admin Panel\n\n{stats}", reply_markup=reply_markup)


# Handle Add Item
async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to add items.")
        return

    await update.message.reply_text("Please send the name of the new item.")
    context.user_data['action'] = 'add_item'


async def process_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('action') == 'add_item':
        item_name = update.message.text
        await update.message.reply_text(f"Enter the file path for {item_name}:")
        context.user_data['item_name'] = item_name
        context.user_data['action'] = 'add_item_path'
        return

    if context.user_data.get('action') == 'add_item_path':
        item_path = update.message.text
        item_price = 0.0005

        ITEMS[f"item{len(ITEMS)+1}"] = {
            'name': context.user_data['item_name'],
            'price_btc': item_price,
            'file_path': item_path
        }

        await update.message.reply_text(f"Item {context.user_data['item_name']} added successfully.")
        context.user_data.clear()


# Remove Item
async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to remove items.")
        return

    keyboard = [
        [InlineKeyboardButton(item['name'], callback_data=f"remove_{key}")] for key, item in ITEMS.items()
    ]
    keyboard.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an item to remove:", reply_markup=reply_markup)


async def confirm_remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    item_key = query.data.split("_")[1]
    if item_key in ITEMS:
        del ITEMS[item_key]
        await query.message.reply_text("Item removed successfully.")
    else:
        await query.message.reply_text("Item not found.")


# Back to Main Menu
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("View Admin Panel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Back to main menu.", reply_markup=reply_markup)


# Handle Button Callbacks
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "admin_panel":
        await admin_panel(update, context)

    elif query.data == "add_item":
        await add_item(update, context)
    elif query.data == "remove_item":
        await remove_item(update, context)
    elif query.data.startswith("remove_"):
        await confirm_remove_item(update, context)
    elif query.data == "back_to_main":
        await back_to_main(update, context)


# Main entry point
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", admin_panel))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Deploy Flask server for Blockonomics callback
    app.run_polling()

    # Run Flask app for Blockonomics webhook
    app_flask.run(debug=True, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
