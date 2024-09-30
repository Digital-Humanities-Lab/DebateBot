import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.conversation_store import conversation_history
from bot.openai_client import openai_client
from bot.utils import generate_verification_code
from database.database_support import (
    insert_user,
    user_exists,
    update_user_email,
    update_user_conversation_state,
    reset_user_registration,
    get_conversation_state,
    get_user_email,
    get_verification_code,
    update_user_debate_info,
    get_user_debate_info,
    delete_user_from_db,
)
from mail.mail_confirmation import send_email
from bot.config import load_config

# Configure logging
logging.basicConfig(level=logging.INFO)

# Define stages for conversation
STARTED = 0
AWAITING_EMAIL = 1
AWAITING_VERIFICATION_CODE = 2
VERIFIED = 3
AWAITING_DEBATE_TOPIC = 4
AWAITING_DEBATE_SIDE = 5
CHAT_GPT = 6

# Mapping from state names to constants
STATE_MAP = {
    'STARTED': STARTED,
    'AWAITING_EMAIL': AWAITING_EMAIL,
    'AWAITING_VERIFICATION_CODE': AWAITING_VERIFICATION_CODE,
    'VERIFIED': VERIFIED,
    'AWAITING_DEBATE_TOPIC': AWAITING_DEBATE_TOPIC,
    'AWAITING_DEBATE_SIDE': AWAITING_DEBATE_SIDE,
    'CHAT_GPT': CHAT_GPT,
}


async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # Check if the user exists in the database
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, it looks like you're new here. Use the /start command to register first."
        )
        return

    # Get the user's conversation state from the database
    conversation_state = get_conversation_state(user_id)

    # Handle based on the conversation state
    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please complete your registration first."
        )

        # return conversation_state
    elif conversation_state == "VERIFIED":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please set your debate topic and side using the /menu command."
        )
    elif conversation_state == "AWAITING_DEBATE_TOPIC":
        # Delegate to receive_topic function
        await receive_topic(update, context)
    elif conversation_state == "AWAITING_DEBATE_SIDE":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please choose your side using the buttons."
        )
    elif conversation_state == "CHAT_GPT":
        # Delegate to gpt_reply function
        await gpt_reply(update, context)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, I didn't understand that."
        )
        
    return conversation_state


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the /start command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if the user exists in the database
    if not user_exists(user_id):
        # New user, insert into database with STARTED status
        insert_user(
            user_id,
            email=None,
            verification_code=None,
            conversation_state="STARTED",
            topic=None,
            side=None,
        )

        # Send a welcome message with a registration button
        keyboard = [[InlineKeyboardButton("Register", callback_data="register")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome! You need to register before using the bot. Please click the button below to register.",
            reply_markup=reply_markup,
        )
        return STARTED

    else:
        # Get the user's conversation state from the database
        conversation_state = get_conversation_state(user_id)

        if conversation_state == "STARTED":
            # User already started but not registered
            keyboard = [[InlineKeyboardButton("Register", callback_data="register")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="You're already started the process. Please register to continue.",
                reply_markup=reply_markup,
            )
            return STARTED

        elif conversation_state == "AWAITING_EMAIL":
            # Include cancel button
            keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_registration")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # User is awaiting email input
            await context.bot.send_message(
                chat_id=chat_id,
                text="Please enter your email address. It should be either '@ehu.lt' or '@student.ehu.lt'.",
                reply_markup=reply_markup,
            )
            return AWAITING_EMAIL

        elif conversation_state == "AWAITING_VERIFICATION_CODE":
            # User is registered but awaiting verification
            keyboard = [
                [InlineKeyboardButton("Resend verification email", callback_data="resend_verification")],
                [InlineKeyboardButton("Cancel", callback_data="cancel_registration")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "You're registered but haven't verified your email. Please enter the verification code "
                    "sent to your email, or click the button below to resend the code."
                ),
                reply_markup=reply_markup,
            )
            return AWAITING_VERIFICATION_CODE

        elif conversation_state == "VERIFIED":
            # User is registered and verified
            await context.bot.send_message(
                chat_id=chat_id,
                text="Welcome back! You're verified and can continue using the bot. Use /menu to change topic or side.",
            )
            return VERIFIED

        elif conversation_state == "AWAITING_DEBATE_TOPIC":
            # User is awaiting debate topic
            await context.bot.send_message(
                chat_id=chat_id,
                text="Please type your debate topic.",
            )
            return AWAITING_DEBATE_TOPIC

        elif conversation_state == "AWAITING_DEBATE_SIDE":
            # User is awaiting debate side
            await context.bot.send_message(
                chat_id=chat_id,
                text="Please choose your side in the debate.",
            )
            return AWAITING_DEBATE_SIDE

        elif conversation_state == "CHAT_GPT":
            # User can use the GPT chat
            await context.bot.send_message(
                chat_id=chat_id,
                text="You can use the bot now! Use /menu to change topic or side.",
            )
            return CHAT_GPT


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the registration process."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Update user's state to 'AWAITING_EMAIL'
    update_user_conversation_state(user_id, "AWAITING_EMAIL")

    # Include cancel button
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_registration")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to enter their email
    await query.edit_message_text(
        text="Please enter your email address. It should be either '@ehu.lt' or '@student.ehu.lt'.",
        reply_markup=reply_markup,
    )

    return AWAITING_EMAIL


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for receiving the email."""
    user_id = update.message.from_user.id
    email = update.message.text.strip()
    logging.info(f"User {user_id} entered email: {email}")

    # Check if the email belongs to the allowed domains
    if not (email.endswith('@ehu.lt') or email.endswith('@student.ehu.lt')):
        logging.warning(f"Invalid email entered by user {user_id}: {email}")

        # Include cancel button
        keyboard = [[InlineKeyboardButton("Cancel", callback_data='cancel_registration')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Invalid email! Please make sure your email is either '@ehu.lt' or '@student.ehu.lt'. Try again.",
            reply_markup=reply_markup
        )
        return AWAITING_EMAIL

    # Generate verification code
    verification_code = generate_verification_code()
    logging.info(f"Generated verification code for user {user_id}: {verification_code}")

    # Update the user's email and verification code in the database
    try:
        update_user_email(user_id, new_email=email, verification_code=verification_code)
        logging.info(f"Updated email and verification code for user {user_id} in the database")
    except Exception as e:
        logging.exception(f"Exception updating user {user_id} in the database")
        await update.message.reply_text(
            "There was an error updating your information. Please try again later."
        )
        return ConversationHandler.END

    try:
        # Send the verification code via email
        send_email(email, verification_code)
        logging.info(f"Sent verification email to {email}")

        # Add buttons to resend the verification code and cancel
        keyboard = [
            [InlineKeyboardButton("Resend verification email", callback_data='resend_verification')],
            [InlineKeyboardButton("Cancel", callback_data='cancel_registration')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Verification code sent to {email}. Please check your email and enter the code here.",
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE

    except Exception as e:
        logging.exception(f"Error sending verification email to {email}")
        await update.message.reply_text(
            "There was an error sending the verification email. Please try again later."
        )
        return ConversationHandler.END


async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for verifying the code."""
    user_id = update.message.from_user.id
    entered_code = update.message.text.strip()

    # Get the correct code from the database
    correct_code = get_verification_code(user_id)

    if correct_code is None:
        await update.message.reply_text("There was an issue retrieving your verification code. Please try again later.")
        return ConversationHandler.END

    if entered_code == str(correct_code):
        # Update the user's state to VERIFIED
        update_user_conversation_state(user_id, 'VERIFIED')

        await update.message.reply_text(
            "Your email has been verified! You can now use the bot.",
        )
        return VERIFIED
    else:
        # Incorrect code
        keyboard = [
            [InlineKeyboardButton("Resend verification email", callback_data='resend_verification')],
            [InlineKeyboardButton("Cancel", callback_data='cancel_registration')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Incorrect code. Please try again or click the button below to resend the verification email.",
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE


async def resend_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for resending the verification email."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Get user's email from the database
    email = get_user_email(user_id)

    # Generate a new verification code
    verification_code = generate_verification_code()
    conversation_state = get_conversation_state(user_id)

    if conversation_state == 'VERIFIED':
        # User is already verified
        await query.edit_message_text("You're verified and can continue using the bot.")
        return ConversationHandler.END
    else:
        try:
            # Send the verification code to the user's email
            send_email(email, verification_code)

            # Update the verification code in the database
            update_user_email(user_id, email, verification_code)

            # Keep the same buttons
            keyboard = [
                [InlineKeyboardButton("Resend verification email", callback_data='resend_verification')],
                [InlineKeyboardButton("Cancel", callback_data='cancel_registration')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Add timestamp for uniqueness
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Edit the existing message with updated text
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"The verification code has been resent to {email} at {timestamp}. Please check your email.",
                reply_markup=reply_markup
            )

        except Exception as e:
            logging.exception("Exception in resend_verification handler")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Failed to resend verification email. Please try again later."
            )
            return ConversationHandler.END

        return AWAITING_VERIFICATION_CODE


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for canceling the registration."""
    query = update.callback_query
    user_id = query.from_user.id

    # Reset the user's registration data
    reset_user_registration(user_id)

    await query.answer()
    # Send a message indicating that registration has been canceled
    await query.edit_message_text(
        text="Registration has been canceled. To start again, please click the Register button.",
    )

    # Send the initial registration prompt with the Register button
    keyboard = [[InlineKeyboardButton("Register", callback_data='register')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Welcome! You need to register before using the bot. Please click the button below to register.",
        reply_markup=reply_markup
    )
    return STARTED


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the /menu command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if user is registered and verified
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, it looks like you are new here. Use the /start command or just write something to register first.",
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please complete your registration first.",
        )
        return None

    # Include buttons to change topic and side
    keyboard = [
        [
            InlineKeyboardButton("Change Topic", callback_data="change_topic"),
            InlineKeyboardButton("Change Side", callback_data="change_side"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=chat_id,
        text="Please choose an option:",
        reply_markup=reply_markup,
    )

    return STATE_MAP.get(conversation_state, VERIFIED)


async def handle_verified_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text messages in VERIFIED state."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if user has set topic and side
    user_info = get_user_debate_info(user_id)
    if user_info and all(user_info):
        # If topic and side are set, update state to CHAT_GPT
        update_user_conversation_state(user_id, 'CHAT_GPT')
        await context.bot.send_message(
            chat_id=chat_id,
            text="You're all set! You can now start the debate."
        )
        return CHAT_GPT
    else:
        # Prompt the user to set topic and side
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please set your debate topic and side using the /menu command."
        )
        return VERIFIED
    

async def change_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to change the debate topic."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    await query.answer()

    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, it looks like you are new here. Use the /start command or just write something to register first.",
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please complete your registration first.",
        )
        return None

    # Save the previous state
    context.user_data["previous_state"] = conversation_state

    update_user_conversation_state(user_id, "AWAITING_DEBATE_TOPIC")

    # Include cancel button
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_change_topic")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to enter the debate topic
    await context.bot.send_message(
        chat_id=chat_id,
        text="Please enter the debate topic.",
        reply_markup=reply_markup,
    )

    return AWAITING_DEBATE_TOPIC


async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to receive the debate topic."""
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    topic = update.message.text.strip()

    user_info = get_user_debate_info(user_id)
    # Update the topic in the database
    update_user_debate_info(user_id, topic, user_info[1])

    # Clear the conversation history
    conversation_history[user_id] = []

    update_user_conversation_state(user_id, 'AWAITING_DEBATE_SIDE')

    # Include cancel button
    keyboard = [
        [InlineKeyboardButton("For", callback_data='for')],
        [InlineKeyboardButton("Against", callback_data='against')],
        [InlineKeyboardButton("Cancel", callback_data='cancel_change_topic')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Ask the user to choose a side (For/Against)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Topic is '{topic}'. Please choose your side.",
        reply_markup=reply_markup
    )

    return AWAITING_DEBATE_SIDE


async def change_side_entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to change the debate side."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    await query.answer()

    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, it looks like you are new here. Use the /start command or just write something to register first.",
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please complete your registration first.",
        )
        return None

    # Save the previous state
    context.user_data["previous_state"] = conversation_state

    update_user_conversation_state(user_id, "AWAITING_DEBATE_SIDE")

    # Include cancel button
    keyboard = [
        [InlineKeyboardButton("For", callback_data="for")],
        [InlineKeyboardButton("Against", callback_data="against")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_change_side")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to choose a side
    await context.bot.send_message(
        chat_id=chat_id,
        text="Please choose your side.",
        reply_markup=reply_markup,
    )

    return AWAITING_DEBATE_SIDE


async def cancel_change_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to cancel changing the topic."""
    query = update.callback_query
    user_id = query.from_user.id

    # Retrieve the previous state
    previous_state = context.user_data.get("previous_state", "VERIFIED")

    # Reset the user's conversation state to the previous state
    update_user_conversation_state(user_id, previous_state)

    await query.answer()
    # Send a message indicating that the topic change has been canceled
    await query.edit_message_text(text="Topic change has been canceled.")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="You can continue using the bot.",
    )

    # Map state strings to constants
    return_state = STATE_MAP.get(previous_state, VERIFIED)

    return return_state


async def cancel_change_side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to cancel changing the side."""
    query = update.callback_query
    user_id = query.from_user.id

    # Retrieve the previous state
    previous_state = context.user_data.get("previous_state", "CHAT_GPT")

    # Reset the user's conversation state to the previous state
    update_user_conversation_state(user_id, previous_state)

    await query.answer()
    # Send a message indicating that the side change has been canceled
    await query.edit_message_text(text="Side change has been canceled.")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="You can continue using the bot.",
    )

    # Map state strings to constants
    return_state = STATE_MAP.get(previous_state, CHAT_GPT)

    return return_state


async def select_side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for selecting a side."""
    query = update.callback_query
    user_id = query.from_user.id
    side = query.data  # 'for' or 'against'

    chat_id = update.effective_chat.id

    if side in ['for', 'against']:
        if not user_exists(user_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="Hi, it looks like you are new here. Use the /start command or just write something to register first."
            )
            return None

        # Update side in the database
        user_info = get_user_debate_info(user_id)
        topic = user_info[0] if user_info else None
        update_user_debate_info(user_id, topic, side)

        # Clear the conversation history
        conversation_history[user_id] = []

        await query.answer()
        await query.edit_message_text(
            text=f"Side set to '{side}'. You can now start the debate!"
        )
        update_user_conversation_state(user_id, 'CHAT_GPT')
        return CHAT_GPT

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Invalid selection. Please choose 'For' or 'Against'."
        )
        return AWAITING_DEBATE_SIDE


async def gpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for GPT chat replies."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()

    # Check if the user is registered and in CHAT_GPT state
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, it looks like you are new here. Use the /start command or just write something to register first.",
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state != "CHAT_GPT":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please finish registration and set your debate topic and side first.",
        )
        return None

    user_info = get_user_debate_info(user_id)
    if not user_info:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please set your debate topic and side.",
        )
        return None

    topic, side = user_info  # Unpack the tuple
    if not topic or not side:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please set your debate topic and side.",
        )
        return None

    debate_topic = topic
    debate_side = side

    # Initialize conversation history if not present
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Add the user's message to the conversation history
    conversation_history[user_id].append({"role": "user", "content": user_message})

    # Get the config from context.bot_data
    config = context.bot_data.get('config', {})

    # Get the prompt and model from the config
    prompt_template = config.get('PROMPT', '')
    gpt_model = config.get('GPT_MODEL', 'gpt-4')

    # Format the prompt with debate_topic and debate_side
    prompt = prompt_template.format(debate_topic=debate_topic, debate_side=debate_side)

    # Add the prompt and conversation history
    messages = [{"role": "system", "content": prompt}] + conversation_history[user_id]

    try:
        # Generate the response using OpenAI GPT, keeping your existing method
        stream = openai_client.chat.completions.create(
            model=gpt_model,
            messages=messages,
            stream=True,
        )

        response = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                response += delta.content

        # Check if the response is empty
        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")

        # Add GPT's response to the conversation history
        conversation_history[user_id].append({"role": "assistant", "content": response})

        # Send the generated reply to the user
        await context.bot.send_message(
            chat_id=chat_id, text=response
        )
    except Exception as e:
        logging.exception("Error during GPT reply")
        await context.bot.send_message(
            chat_id=chat_id, text="Sorry, there was an error processing your request."
        )

    return CHAT_GPT


async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /delete command to remove user data."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Delete user data from the database
    delete_user_from_db(user_id)

    # Remove user from conversation history if present
    conversation_history.pop(user_id, None)

    await context.bot.send_message(
        chat_id=chat_id,
        text="Your data has been deleted. To start again, use the /start command.",
    )

    return ConversationHandler.END