from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from bot.utils import *
from database.database_support import *
from mail.mail_confirmation import *

# Define stages for conversation
AWAITING_EMAIL = 1
AWAITING_VERIFICATION_CODE = 2
VERIFIED = 3

# Define your handler for the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if the user exists in the database
    if not user_exists(user_id):
        # User doesn't exist, send a welcome message and registration button
        keyboard = [[InlineKeyboardButton("Register", callback_data='register')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome! You need to register before using the bot. Please click the button below to register.",
            reply_markup=reply_markup
        )
    else:
        # Get the user's conversation state from the database
        conversation_state = get_conversation_state(user_id)

        if conversation_state == 'AWAITING_VERIFICATION_CODE':
            # User is registered but awaiting verification
            keyboard = [[InlineKeyboardButton("Resend verification email", callback_data='resend_verification')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="You're registered but haven't verified your email. Please enter the verification code sent to your email, or click the button below to resend the code.",
                reply_markup=reply_markup
            )

        elif conversation_state == 'VERIFIED':
            # User is registered and verified
            await context.bot.send_message(
                chat_id=chat_id,
                text="Welcome back! You're verified and can continue using the bot."
            )

# Start the registration process
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # Insert the user into the database with the status 'AWAITING_EMAIL'
    insert_user(user_id, email=None, verification_code=None, conversation_state='AWAITING_EMAIL')

    # Prompt the user to enter their email
    await query.edit_message_text(
        text="Please enter your email address. It should be either '@ehu.lt' or '@student.ehu.lt'."
    )
    return AWAITING_EMAIL

# Handler for receiving the email
async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    email = update.message.text.strip()

    # Check if the email belongs to the allowed domains
    if not (email.endswith('@ehu.lt') or email.endswith('@student.ehu.lt')):
        await update.message.reply_text(
            "Invalid email! Please make sure your email is either '@ehu.lt' or '@student.ehu.lt'. Try again."
        )
        return AWAITING_EMAIL

    # Generate verification code
    verification_code = generate_verification_code()

    # Update the user's email and status in the database
    update_user_email(user_id, new_email=email, verification_code=verification_code)

    try:
        # Send the verification code via email
        send_email(email, verification_code)
        # Add a button to resend the verification code
        keyboard = [[InlineKeyboardButton("Resend verification email", callback_data='resend_verification')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Verification code sent to {email}. Please check your email and enter the code here.",
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE

    except Exception as e:
        await update.message.reply_text(
            "There was an error sending the verification email. Please try again later."
        )
        return ConversationHandler.END

# Fallback for invalid inputs or cancelling the process
async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Registration canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Handler for verifying the code
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    entered_code = update.message.text.strip()

    # Get the correct code from the database
    correct_code = get_verification_code(user_id)

    if correct_code is None:
        await update.message.reply_text("There was an issue retrieving your verification code. Please try again later.")
        return ConversationHandler.END

    if entered_code == str(correct_code):
        # Update the user's state to VERIFIED
        update_user_verification_status(user_id, is_verified=True)
        await update.message.reply_text("Your email has been verified! You can now use the bot.")
        return ConversationHandler.END
    else:
        # Incorrect code
        keyboard = [[InlineKeyboardButton("Resend verification email", callback_data='resend_verification')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Incorrect code. Please try again or click the button below to resend the verification email.",
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE

# Handler for resending verification email
async def resend_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id

    # Get the user's email from the database
    email = get_user_email(user_id)

    # Generate a new verification code
    verification_code = generate_verification_code()
    conversation_state = get_conversation_state(user_id)

    if conversation_state == 'VERIFIED':
        # User is registered and verified
        await query.edit_message_text("You're verified and can continue using the bot.")
        return ConversationHandler.END
    else:
        try:
            # Send the verification code to the user's email
            send_email(email, verification_code)

            # Update the verification code in the database
            update_user_email(user_id, email, verification_code)

            # Keep the button intact, just edit the message text
            await query.edit_message_text(
                f"Verification code resent to {email}. Please check your email.",
                reply_markup=query.message.reply_markup  # Reuse the same button
            )

        except Exception as e:
            await query.edit_message_text("Failed to resend verification email. Please try again later.")
            return ConversationHandler.END

        return AWAITING_VERIFICATION_CODE

