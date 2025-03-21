import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.conversation_store import conversation_history
from bot.openai_client import openai_client
from bot.utils import generate_verification_code, load_messages
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
    update_user_language,
    get_user_language,
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
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Check if the user exists in the database
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["not_registered"]
        )
        return

    # Get the user's conversation state from the database
    conversation_state = get_conversation_state(user_id)

    # Handle based on the conversation state
    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["complete_registration"]
        )
    elif conversation_state == "VERIFIED":
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["set_topic_side"]
        )
    elif conversation_state == "AWAITING_DEBATE_TOPIC":
        # Delegate to receive_topic function
        await receive_topic(update, context)
    elif conversation_state == "AWAITING_DEBATE_SIDE":
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["side_prompt"]
        )
    elif conversation_state == "CHAT_GPT":
        # Delegate to gpt_reply function
        await gpt_reply(update, context)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["error_processing"]
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
            language=None
        )

        # Prompt the user to select a language
        keyboard = [
            [InlineKeyboardButton("English", callback_data="language_en")],
            [InlineKeyboardButton("Русский", callback_data="language_ru")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome! Please choose your language:\nДобро пожаловать! Пожалуйста, выберите язык:",
            reply_markup=reply_markup,
        )
        return STARTED

    else:
        # Get user's language
        language = get_user_language(user_id)
        msgs = load_messages(language)

        # Get the user's conversation state from the database
        conversation_state = get_conversation_state(user_id)

        if conversation_state == "STARTED":
            # User already started but not registered
            keyboard = [[InlineKeyboardButton(msgs["register_button"], callback_data="register")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["register_prompt"],
                reply_markup=reply_markup,
            )
            return STARTED

        elif conversation_state == "AWAITING_EMAIL":
            # Include cancel button
            keyboard = [[InlineKeyboardButton(msgs["cancel_button"], callback_data="cancel_registration")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # User is awaiting email input
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["enter_email_prompt"],
                reply_markup=reply_markup,
            )
            return AWAITING_EMAIL

        elif conversation_state == "AWAITING_VERIFICATION_CODE":
            # User is registered but awaiting verification
            keyboard = [
                [InlineKeyboardButton(msgs["resend_verification"], callback_data="resend_verification")],
                [InlineKeyboardButton(msgs["cancel_button"], callback_data="cancel_registration")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            email = get_user_email(user_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["verification_sent"].format(email=email),
                reply_markup=reply_markup,
            )
            return AWAITING_VERIFICATION_CODE

        elif conversation_state == "VERIFIED":
            # User is registered and verified
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["welcome_back"],
            )
            return VERIFIED

        elif conversation_state == "AWAITING_DEBATE_TOPIC":
            # User is awaiting debate topic
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["topic_prompt"],
            )
            return AWAITING_DEBATE_TOPIC

        elif conversation_state == "AWAITING_DEBATE_SIDE":
            # User is awaiting debate side
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["side_prompt"],
            )
            return AWAITING_DEBATE_SIDE

        elif conversation_state == "CHAT_GPT":
            # User can use the GPT chat
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["you_can_use_bot"],
            )
            return CHAT_GPT


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for receiving the email."""
    user_id = update.message.from_user.id
    email = update.message.text.strip()
    language = get_user_language(user_id)
    msgs = load_messages(language)
    logging.info(f"User {user_id} entered email: {email}")

    # Check if the email belongs to the allowed domains
    if not (email.endswith('@ehu.lt') or email.endswith('@student.ehu.lt')):
        logging.warning(f"Invalid email entered by user {user_id}: {email}")

        # Include cancel button
        keyboard = [[InlineKeyboardButton(msgs["cancel_button"], callback_data='cancel_registration')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            msgs["invalid_email"],
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
            msgs["error_processing"]
        )
        return ConversationHandler.END

    try:
        # Send the verification code via email
        send_email(email, verification_code)
        logging.info(f"Sent verification email to {email}")

        # Add buttons to resend the verification code and cancel
        keyboard = [
            [InlineKeyboardButton(msgs["resend_verification"], callback_data='resend_verification')],
            [InlineKeyboardButton(msgs["cancel_button"], callback_data='cancel_registration')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            msgs["verification_sent"].format(email=email),
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE

    except Exception as e:
        logging.exception(f"Error sending verification email to {email}")
        await update.message.reply_text(
            msgs["error_processing"]
        )
        return ConversationHandler.END


async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for verifying the code."""
    user_id = update.message.from_user.id
    entered_code = update.message.text.strip()
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Get the correct code from the database
    correct_code = get_verification_code(user_id)

    if correct_code is None:
        await update.message.reply_text(msgs["error_processing"])
        return ConversationHandler.END

    if entered_code == str(correct_code):
        # Update the user's state to VERIFIED
        update_user_conversation_state(user_id, 'VERIFIED')

        await update.message.reply_text(
            msgs["verified"],
        )
        return VERIFIED
    else:
        # Incorrect code
        keyboard = [
            [InlineKeyboardButton(msgs["resend_verification"], callback_data='resend_verification')],
            [InlineKeyboardButton(msgs["cancel_button"], callback_data='cancel_registration')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            msgs["incorrect_code"],
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE


async def resend_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for resending the verification email."""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    await query.answer()

    # Get user's email from the database
    email = get_user_email(user_id)

    # Generate a new verification code
    verification_code = generate_verification_code()
    conversation_state = get_conversation_state(user_id)

    if conversation_state == 'VERIFIED':
        # User is already verified
        await query.edit_message_text(msgs["verified"])
        return ConversationHandler.END
    else:
        try:
            # Send the verification code to the user's email
            send_email(email, verification_code)

            # Update the verification code in the database
            update_user_email(user_id, email, verification_code)

            # Keep the same buttons
            keyboard = [
                [InlineKeyboardButton(msgs["resend_verification"], callback_data='resend_verification')],
                [InlineKeyboardButton(msgs["cancel_button"], callback_data='cancel_registration')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Add timestamp for uniqueness
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Edit the existing message with updated text
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=msgs["verification_resent"].format(email=email, timestamp=timestamp),
                reply_markup=reply_markup
            )

        except Exception as e:
            logging.exception("Exception in resend_verification handler")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msgs["failed_resend"]
            )
            return ConversationHandler.END

        return AWAITING_VERIFICATION_CODE


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for canceling the registration."""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Reset the user's registration data
    reset_user_registration(user_id)

    await query.answer()
    # Send a message indicating that registration has been canceled
    await query.edit_message_text(
        text=msgs["registration_canceled"],
    )

    # Send the initial registration prompt with the Register button
    keyboard = [[InlineKeyboardButton(msgs["register_button"], callback_data='register')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msgs["register_prompt"],
        reply_markup=reply_markup
    )
    return STARTED


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the /menu command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Check if user is registered and verified
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["not_registered"],
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["complete_registration"],
        )
        return None

    # Include buttons to change topic and side
    keyboard = [
        [
            InlineKeyboardButton(msgs["change_topic_button"], callback_data="change_topic"),
            InlineKeyboardButton(msgs["change_side_button"], callback_data="change_side"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=chat_id,
        text=msgs["choose_option"],
        reply_markup=reply_markup,
    )

    return STATE_MAP.get(conversation_state, VERIFIED)


async def handle_verified_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text messages in VERIFIED state."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Check if user has set topic and side
    user_info = get_user_debate_info(user_id)
    if user_info and all(user_info):
        # If topic and side are set, update state to CHAT_GPT
        update_user_conversation_state(user_id, 'CHAT_GPT')
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["debate_ready"]
        )
        return CHAT_GPT
    else:
        # Prompt the user to set topic and side
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["set_topic_side"]
        )
        return VERIFIED


async def change_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to change the debate topic."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    await query.answer()

    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["not_registered"],
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["complete_registration"],
        )
        return None

    # Save the previous state
    context.user_data["previous_state"] = conversation_state

    update_user_conversation_state(user_id, "AWAITING_DEBATE_TOPIC")

    # Include cancel button
    keyboard = [[InlineKeyboardButton(msgs["cancel_button"], callback_data="cancel_change_topic")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to enter the debate topic
    await context.bot.send_message(
        chat_id=chat_id,
        text=msgs["topic_prompt"],
        reply_markup=reply_markup,
    )

    return AWAITING_DEBATE_TOPIC


async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to receive the debate topic."""
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    topic = update.message.text.strip()
    language = get_user_language(user_id)
    msgs = load_messages(language)

    user_info = get_user_debate_info(user_id)
    # Update the topic in the database
    update_user_debate_info(user_id, topic, user_info[1])

    # Clear the conversation history
    conversation_history[user_id] = []

    update_user_conversation_state(user_id, 'AWAITING_DEBATE_SIDE')

    # Include cancel button
    keyboard = [
        [InlineKeyboardButton(msgs["for_button"], callback_data='for')],
        [InlineKeyboardButton(msgs["against_button"], callback_data='against')],
        [InlineKeyboardButton(msgs["cancel_button"], callback_data='cancel_change_topic')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Ask the user to choose a side (For/Against)
    await context.bot.send_message(
        chat_id=chat_id,
        text=msgs["topic_set"].format(topic=topic),
        reply_markup=reply_markup
    )

    return AWAITING_DEBATE_SIDE


async def change_side_entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to change the debate side."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    await query.answer()

    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["not_registered"],
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state in ("STARTED", "AWAITING_EMAIL", "AWAITING_VERIFICATION_CODE"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["complete_registration"],
        )
        return None

    # Save the previous state
    context.user_data["previous_state"] = conversation_state

    update_user_conversation_state(user_id, "AWAITING_DEBATE_SIDE")

    # Include cancel button
    keyboard = [
        [InlineKeyboardButton(msgs["for_button"], callback_data="for")],
        [InlineKeyboardButton(msgs["against_button"], callback_data="against")],
        [InlineKeyboardButton(msgs["cancel_button"], callback_data="cancel_change_side")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to choose a side
    await context.bot.send_message(
        chat_id=chat_id,
        text=msgs["side_prompt"],
        reply_markup=reply_markup,
    )

    return AWAITING_DEBATE_SIDE


async def cancel_change_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to cancel changing the topic."""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Retrieve the previous state
    previous_state = context.user_data.get("previous_state", "VERIFIED")

    # Reset the user's conversation state to the previous state
    update_user_conversation_state(user_id, previous_state)

    await query.answer()
    # Send a message indicating that the topic change has been canceled
    await query.edit_message_text(text=msgs["topic_change_canceled"])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msgs["continue_using_bot"],
    )

    # Map state strings to constants
    return_state = STATE_MAP.get(previous_state, VERIFIED)

    return return_state


async def cancel_change_side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler to cancel changing the side."""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Retrieve the previous state
    previous_state = context.user_data.get("previous_state", "CHAT_GPT")

    # Reset the user's conversation state to the previous state
    update_user_conversation_state(user_id, previous_state)

    await query.answer()
    # Send a message indicating that the side change has been canceled
    await query.edit_message_text(text=msgs["side_change_canceled"])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msgs["continue_using_bot"],
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
    language = get_user_language(user_id)
    msgs = load_messages(language)

    if side in ['for', 'against']:
        if not user_exists(user_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["not_registered"]
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
            text=msgs["side_set"].format(side=side)
        )
        update_user_conversation_state(user_id, 'CHAT_GPT')
        return CHAT_GPT

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["invalid_selection"]
        )
        return AWAITING_DEBATE_SIDE


async def gpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for GPT chat replies."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()
    language = get_user_language(user_id)
    msgs = load_messages(language)

    # Check if the user is registered and in CHAT_GPT state
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["not_registered"],
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state != "CHAT_GPT":
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["finish_registration"],
        )
        return None

    user_info = get_user_debate_info(user_id)
    if not user_info:
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["set_topic_side"],
        )
        return None

    topic, side = user_info  # Unpack the tuple
    if not topic or not side:
        await context.bot.send_message(
            chat_id=chat_id,
            text=msgs["set_topic_side"],
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
    print(f"Prompt template: {prompt_template}")  # Debug print statement

    gpt_model = config.get('GPT_MODEL', '')

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
            chat_id=chat_id, text=msgs["error_processing"]
        )

    return CHAT_GPT


async def change_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the /language command to change the user's language preference."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Retrieve user's current conversation state
    conversation_state = get_conversation_state(user_id)
    if conversation_state is None:
        conversation_state = 'STARTED'

    # Store the previous state in user_data
    context.user_data['previous_state'] = conversation_state

    # Prompt the user to select a language
    keyboard = [
        [InlineKeyboardButton("English", callback_data="language_en")],
        [InlineKeyboardButton("Русский", callback_data="language_ru")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=chat_id,
        text="Please choose your language:\nПожалуйста, выберите язык:",
        reply_markup=reply_markup,
    )
    # Return the current state to stay in the conversation
    return STATE_MAP.get(conversation_state, STARTED)


async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for selecting language preference."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = update.effective_chat.id
    data = query.data  # 'language_en' or 'language_ru'

    await query.answer()

    # Determine the selected language
    if data == 'language_en':
        language = 'en'
    elif data == 'language_ru':
        language = 'ru'
    else:
        # Invalid selection
        return ConversationHandler.END

    # Update user's language in the database
    update_user_language(user_id, language)

    # Load messages in the selected language
    msgs = load_messages(language)

    # Now inform the user
    msg = msgs['language_changed']
    await query.edit_message_text(
        text=msg,
    )

    # Get the user's conversation state from the database
    conversation_state = get_conversation_state(user_id)
    # Check if the user is registered
    if conversation_state == "STARTED":
            # User already started but not registered
            keyboard = [[InlineKeyboardButton(msgs["register_button"], callback_data="register")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text=msgs["register_prompt"],
                reply_markup=reply_markup,
            )
            return STARTED
    
    # Retrieve previous state
    previous_state = context.user_data.get('previous_state', 'STARTED')
    # Return to the previous state
    return STATE_MAP.get(previous_state, STARTED)


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the registration process."""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(user_id)
    msgs = load_messages(language)

    await query.answer()

    # Update user's state to 'AWAITING_EMAIL'
    update_user_conversation_state(user_id, "AWAITING_EMAIL")

    # Include cancel button
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_registration")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to enter their email
    await query.edit_message_text(
        text=msgs["enter_email_prompt"],
        reply_markup=reply_markup,
    )

    return AWAITING_EMAIL


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