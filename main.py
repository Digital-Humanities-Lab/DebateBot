from telegram.ext import Application, CommandHandler, MessageHandler, filters
from bot.config import load_config
from bot.handlers import *
from mail.mail_confirmation import *

def main() -> None:
    """Start the bot."""
    # Load configuration
    config = load_config()

    # Create the Application and pass it your bot's token from config.txt
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    # Add handlers for start command and user messages
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("verify", verify))
    application.add_handler(CommandHandler("send", send))
    application.add_handler(CommandHandler("change_email", change_email))
    application.add_handler(CommandHandler("choose_topic", choose_topic))
    application.add_handler(CommandHandler("choose_side", choose_side))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_reply))

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
