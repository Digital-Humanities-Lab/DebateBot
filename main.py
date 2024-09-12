from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
from bot.config import load_config
from bot.handlers import *
from mail.mail_confirmation import *

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

def main() -> None:
    """Start the bot."""
    # Load configuration
    config = load_config()

    # Create the Application and pass it your bot's token from config.txt
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    # Register command and callback handlers
    application.add_handler(CommandHandler("start", start))

    register_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(register, pattern='register'), CallbackQueryHandler(resend_verification, pattern='resend_verification')],
        states={
            AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
            AWAITING_VERIFICATION_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_code),
                                         CallbackQueryHandler(resend_verification, pattern='resend_verification')],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_registration)],
        per_chat=True  # Ensure conversation is tracked per chat
    )

    # Register conversation handler
    application.add_handler(register_conv_handler)

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
