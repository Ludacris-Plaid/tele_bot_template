import os
import asyncio
import requests
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

# Admin interface
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to access this panel.")
        return

    # Admin Stats - You can pull more dynamic stats here
    stats = f"Total items: {len(ITEMS)}\nTotal revenue: 0 BTC"  # Placeholder for stats

    # Displaying stats and options in "popup-like" format using inline keyboard
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

    # Asking for file name and price
    await update.message.reply_text("Please send the name of the new item.")

    # Save the state to request further information
    context.user_data['action'] = 'add_item'

async def process_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('action') == 'add_item':
        item_name = update.message.text  # Get item name
        await update.message.reply_text(f"Enter the file path for {item_name}:")
        context.user_data['item_name'] = item_name
        context.user_data['action'] = 'add_item_path'
        return

    if context.user_data.get('action') == 'add_item_path':
        item_path = update.message.text  # Get file path
        item_price = 0.0005  # Dummy value for now; You could extend this for more info

        # Add the new item
        ITEMS[f"item{len(ITEMS)+1}"] = {
            'name': context.user_data['item_name'],
            'price_btc': item_price,
            'file_path': item_path
        }

        await update.message.reply_text(f"Item {context.user_data['item_name']} added successfully.")
        context.user_data.clear()  # Clear temporary data

# Remove Item
async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to remove items.")
        return

    # List items for removal
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

    # Admin Panel button press
    if query.data == "admin_panel":
        await admin_panel(update, context)

    # Add Item or Remove Item logic
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

    app.run_polling()

if __name__ == "__main__":
    main()
