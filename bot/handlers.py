from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from bot.conversation_store import conversation_history
from bot.openai_client import openai_client
from bot.utils import *
from database.database_support import *
from mail.mail_confirmation import *

user_debate_info = {}  # To store topic and side for each user

# Define stages for conversation
STARTED = 0
AWAITING_EMAIL = 1
AWAITING_VERIFICATION_CODE = 2
VERIFIED = 3
AWAITING_DEBATE_TOPIC = 4
AWAITING_DEBATE_SIDE = 5
CHAT_GPT = 6


# Define your handler for the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if the user exists in the database
    if not user_exists(user_id):
        # New user, insert into database with STARTED status
        insert_user(user_id, email=None, verification_code=None, conversation_state='STARTED', topic=None, side=None)

        # Send a welcome message with a registration button
        keyboard = [[InlineKeyboardButton("Register", callback_data='register')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome! You need to register before using the bot. Please click the button below to register.",
            reply_markup=reply_markup
        )
        return STARTED
    else:
        # Get the user's conversation state from the database
        conversation_state = get_conversation_state(user_id)

        if conversation_state == 'STARTED':
            # User already started but not registered
            keyboard = [[InlineKeyboardButton("Register", callback_data='register')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="You're already started the process. Please register to continue.",
                reply_markup=reply_markup
            )
            return STARTED

        elif conversation_state == 'AWAITING_EMAIL':
            # User is awaiting email input
            await context.bot.send_message(
                chat_id=chat_id,
                text="Please enter your email address. It should be either '@ehu.lt' or '@student.ehu.lt'."
            )
            return AWAITING_EMAIL

        elif conversation_state == 'AWAITING_VERIFICATION_CODE':
            # User is registered but awaiting verification
            keyboard = [[InlineKeyboardButton("Resend verification email", callback_data='resend_verification')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="You're registered but haven't verified your email. Please enter the verification code sent to your email, or click the button below to resend the code.",
                reply_markup=reply_markup
            )
            return AWAITING_VERIFICATION_CODE

        elif conversation_state == 'VERIFIED':
            # User is registered and verified
            await context.bot.send_message(
                chat_id=chat_id,
                text="Welcome back! You're verified and can continue using the bot.",
            )
            return VERIFIED
        
        elif conversation_state == 'AWAITING_DEBATE_TOPIC':
            # User is registered and AWAITING_DEBATE_TOPIC
            await context.bot.send_message(
                chat_id=chat_id,
                text="Please type your debate topic",
            )
            return AWAITING_DEBATE_TOPIC
        
        elif conversation_state == 'AWAITING_DEBATE_SIDE':
            # User is registered and AWAITING_DEBATE_TOPIC
            await context.bot.send_message(
                chat_id=chat_id,
                text="Please type your side on debates",
            )
            return AWAITING_DEBATE_SIDE
        
        elif conversation_state == 'CHAT_GPT':
            # User is registered and can use CHAT_GPT
            await context.bot.send_message(
                chat_id=chat_id,
                text="You can use our bot now!",
            )
            return CHAT_GPT

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    
    # Update user's status to 'AWAITING_EMAIL'
    update_user_verification_status(user_id, 'AWAITING_EMAIL')

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
        update_user_verification_status(user_id, 'VERIFIED')

        await update.message.reply_text(
            "Your email has been verified! You can now use the bot.",
        )
        return VERIFIED
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
        # User is already verified
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

# Fallback for canceling registration
async def stop_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

    await update.message.reply_text("Registration stoped.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def change_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, looks like you are new here, use the /start command or just write something to register first"
        )
        return None
    
    elif get_conversation_state(user_id) in ('STARTED', 'AWAITING_EMAIL', 'AWAITING_VERIFICATION_CODE'):
            # User already started but not registered
            await context.bot.send_message(
                chat_id=chat_id,
                text="Looks like you are started registration but did not finish. Please write /start or just a message to continue registration",
            )
            return None
    
    update_user_verification_status(user_id, 'AWAITING_DEBATE_TOPIC')
    # Prompt the user to enter the debate topic
    await context.bot.send_message(
        chat_id=chat_id,
        text="Please enter the debate topic."
    )
    
    return AWAITING_DEBATE_TOPIC

# Handler to receive the debate topic
async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    topic = update.message.text.strip()

    # Store the topic in the local dictionary
    user_debate_info[user_id] = {'topic': topic}

    # Update the topic in the database
    update_user_debate_info(user_id, topic, None)

    update_user_verification_status(user_id, 'AWAITING_DEBATE_SIDE')

    # Ask the user to choose a side (For/Against)
    keyboard = [
        [InlineKeyboardButton("For", callback_data='for')],
        [InlineKeyboardButton("Against", callback_data='against')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Topic is '{topic}'. Please choose your side.",
        reply_markup=reply_markup
    )
    
    return AWAITING_DEBATE_SIDE

# Handler for selecting a side
async def change_side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = update.effective_chat.id
    side = query.data  # 'for' or 'against'

    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, looks like you are new here, use the /start command or just write something to register first"
        )
        return None
    
    elif get_conversation_state(user_id) in ('STARTED', 'AWAITING_EMAIL', 'AWAITING_VERIFICATION_CODE'):
            # User already started but not registered
            await context.bot.send_message(
                chat_id=chat_id,
                text="Looks like you are started registration but did not finish. Please write /start or just a message to continue registration",
            )
            return None

    # Update side in the local dictionary
    if user_id in user_debate_info:
        user_debate_info[user_id]['side'] = side

    # Update side in the database
    update_user_debate_info(user_id, user_debate_info[user_id]['topic'], side)

    await query.answer()
    await query.edit_message_text(
        text=f"Side set to '{side}'. You can now start the debate!"
    )
    update_user_verification_status(user_id, 'CHAT_GPT') 
    return CHAT_GPT

# Handler for GPT chat
async def gpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_message = update.message.text.strip()

    # Check if the user is registered and in CHAT_GPT state
    if not user_exists(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Hi, looks like you are new here. Use the /start command or just write something to register first."
        )
        return None

    conversation_state = get_conversation_state(user_id)

    if conversation_state != 'CHAT_GPT':
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please finish registration and set your debate topic and side first using /change_topic."
        )
        return None

    user_info = get_user_debate_info(user_id)
    if not user_info:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please set your debate topic and side using /change_topic."
        )
        return None

    topic, side = user_info  # Unpack the tuple
    if not topic or not side:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please set your debate topic and side using /change_topic."
        )
        return None

    debate_topic = topic
    debate_side = side

    # Initialize conversation history if not present
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Add the user's message to the conversation history
    conversation_history[user_id].append({"role": "user", "content": user_message})

    # Use GPT to generate a reply, focused only on the debate topic
    prompt = f"You are helping a student prepare for a debate. The topic is '{debate_topic}', and the student is arguing '{debate_side}' it. Provide helpful advice, ideas, and counterarguments to support their position."

    # Add the prompt and conversation history
    messages = [{"role": "system", "content": prompt}] + conversation_history[user_id]

    try:
        stream = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}] + messages,
        stream=True,
    )
        response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                response += chunk.choices[0].delta.content

        # Add GPT's response to the conversation history
        conversation_history[user_id].append({"role": "assistant", "content": response})

        # Send the generated reply to the user
        await context.bot.send_message(
            chat_id=chat_id,
            text=response
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, there was an error processing your request."
        )

    return CHAT_GPT



