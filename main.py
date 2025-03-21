from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)

from bot.config import load_config
from bot.handlers import (
    STARTED,
    AWAITING_EMAIL,
    AWAITING_VERIFICATION_CODE,
    VERIFIED,
    AWAITING_DEBATE_TOPIC,
    AWAITING_DEBATE_SIDE,
    CHAT_GPT,
    start,
    menu,
    register,
    cancel_registration,
    receive_email,
    verify_code,
    resend_verification,
    change_topic,
    change_side_entry_point,
    cancel_change_topic,
    cancel_change_side,
    select_side,
    receive_topic,
    gpt_reply,
    handle_verified_text,
    global_message_handler,
    delete_user,
    change_language_command,
    select_language,
)

filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning
)

def main() -> None:
    """Start the bot."""
    # Load configuration
    config = load_config()

    # Create the Application and pass it your bot's token from config.txt
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    application.bot_data['config'] = config

    # Register command handlers
    application.add_handler(CommandHandler("delete", delete_user))

    # Define the conversation handler with states
    register_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("menu", menu),
            CommandHandler("language", change_language_command),
            CallbackQueryHandler(register, pattern="^register$"),
        ],
        states={
            STARTED: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                CallbackQueryHandler(register, pattern="^register$"),
                CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$"),
            ],
            AWAITING_EMAIL: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email),
                CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$"),
        ],
            AWAITING_VERIFICATION_CODE: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_code),
                CallbackQueryHandler(resend_verification, pattern="^resend_verification$"),
                CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$"),
            ],
            VERIFIED: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                CallbackQueryHandler(change_topic, pattern="^change_topic$"),
                CallbackQueryHandler(change_side_entry_point, pattern="^change_side$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_verified_text),
            ],
            AWAITING_DEBATE_TOPIC: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_topic),
                CallbackQueryHandler(cancel_change_topic, pattern="^cancel_change_topic$"),
            ],
            AWAITING_DEBATE_SIDE: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                CallbackQueryHandler(select_side, pattern="^(for|against)$"),
                CallbackQueryHandler(cancel_change_topic, pattern="^cancel_change_topic$"),
                CallbackQueryHandler(cancel_change_side, pattern="^cancel_change_side$"),
            ],
            CHAT_GPT: [
                CallbackQueryHandler(select_language, pattern="^language_(en|ru)$"),
                CallbackQueryHandler(change_topic, pattern="^change_topic$"),
                CallbackQueryHandler(change_side_entry_point, pattern="^change_side$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_reply),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$"),
            CallbackQueryHandler(cancel_change_topic, pattern="^cancel_change_topic$"),
            CallbackQueryHandler(cancel_change_side, pattern="^cancel_change_side$"),
        ],
        per_chat=True,
        allow_reentry=True,
    )

    # Register the conversation handler
    application.add_handler(register_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))

    # Run the bot
    application.run_polling()


if __name__ == "__main__":
    main()
