from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
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
        entry_points=[CommandHandler("start", start),CommandHandler("change_topic", change_topic), MessageHandler(filters.TEXT & ~filters.COMMAND, start), CallbackQueryHandler(register, pattern='register')],
        states={
            STARTED: [CallbackQueryHandler(register, pattern='register')],
            AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
            AWAITING_VERIFICATION_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_code),
                CallbackQueryHandler(resend_verification, pattern='resend_verification')],
            VERIFIED: [
                CommandHandler("change_topic", change_topic),
                CommandHandler("change_side", change_side),
            ],
            AWAITING_DEBATE_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_topic)],
            AWAITING_DEBATE_SIDE: [CallbackQueryHandler(change_side)],
            CHAT_GPT: [
                CommandHandler("change_topic", change_topic),
                CommandHandler("change_side", change_side),
                MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_reply)
            ]  
        },
        fallbacks=[MessageHandler(filters.COMMAND, stop_registration)],
        per_chat=True
    )


    # Register conversation handler
    application.add_handler(register_conv_handler)

    # Add the general text message handler after the conversation handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start)) 

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()