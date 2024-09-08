from telegram import Update
from telegram.ext import ContextTypes
from bot.openai_client import openai_client
from bot.conversation_store import conversation_history
from database.database_support import *
from bot.utils import generate_verification_code 
from mail.mail_confirmation import send_email
import random, re

debate_preferences = {}

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    user_record = get_user(user_id)

    if user_record is None:
        await send_message(update, "Welcome! It looks like you're new here. Please register using the /register command and provide your email.")
    else:
        is_verified = user_record[3]
        if not is_verified:
            await send_verification_prompt(update)
        else:
            await send_message(update, "Hello again! You're already verified and can use the bot.")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    message = update.message.text

    existing_user = get_user(user_id)
    if existing_user:
        await send_message(update, "You are already registered. If you need to update your email use /change_email command.")
        return

    email = extract_email(update, message)
    if not email:
        await send_message(update, "Invalid email format. Please use an email address ending with @ehu.lt.")
        return

    verification_code = generate_verification_code()

    if add_user(user_id, email, verification_code=verification_code):
        send_email(email, verification_code)
        await send_message(update, "You have been registered successfully. Please check your email for a verification code.")
    else:
        await send_message(update, "There was an error with the registration process. Please try again later.")

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    message = update.message.text

    user_record = get_user(user_id)

    if user_record is None:
        await send_message(update, "You are not registered. Please use the /register command to register first.")
        return

    if user_record[3]:
        await send_message(update, "You are already verified and can use the bot.")
        return

    code = extract_code(update, message)
    if code == user_record[2]:
        if update_user_verification_status(user_id, True):
            await send_message(update, "Your email has been successfully verified. You can now use the bot.")
        else:
            await send_message(update, "There was an error verifying your email. Please try again later.")
    else:
        await send_message(update, "Invalid verification code. Please make sure you entered the correct code sent to your email.\nUse /send command to resend code to your email.")

async def change_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    message = update.message.text

    new_email = extract_email(update, message)
    if not new_email:
        await send_message(update, "Invalid email format. Please use an email address ending with @ehu.lt.")
        return

    user_record = get_user(user_id)
    if user_record is None:
        await send_message(update, "You are not registered. Please use the /register command to register first.")
        return
    
    new_verification_code = generate_verification_code()

    if update_user_email(user_id, new_email) and update_user_verification_status(user_id, False) and set_verification_code(user_id, new_verification_code):
        send_email(new_email, new_verification_code)
        await send_message(update, "Your email address has been updated. Please check your new email for a verification code to complete the process.")
    else:
        await send_message(update, "There was an error updating your email address. Please try again later.")

async def send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    user_record = get_user(user_id)
    if user_record is None:
        await send_message(update, "You are not registered. Please use the /register command to register first.")
        return

    if user_record[3]:
        await send_message(update, "You are already verified. There is no need to resend the verification code.")
        return
    email = user_record[1]
    verification_code = user_record[2]
    send_email(email, verification_code)
    await send_message(update, "A new verification code has been sent to your email. Please check your inbox.")

async def send_message(update: Update, text: str) -> None:
    if update.message:
        await update.message.reply_text(text)

def extract_email(update: Update, message: str) -> str:
    try:
        _, email = message.split(maxsplit=1)
        if re.match(EMAIL_REGEX, email):
            return email
        return None
    except ValueError:
        return None

def extract_code(update: Update, message: str) -> str:
    try:
        _, code = message.split(maxsplit=1)
        return code
    except ValueError:
        return None

async def send_verification_prompt(update: Update) -> None:
    await send_message(update,
        "You're currently registered but haven't verified your email yet.\n"
        "To verify, please use the /verify command with the code sent to your email.\n"
        "If you didn't receive the code, you can request a new one using the /send command.\n"
        "If you need to update your email address, use the /change_email command."
    )

async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    message = update.message.text

    # Extract the topic from the message
    try:
        _, topic = message.split(maxsplit=1)
        
        # Check if the user already has a topic chosen and clear conversation history
        if user_id in debate_preferences:
            if debate_preferences[user_id]['topic'] != topic:
                # New topic chosen, clear conversation history and reset side
                conversation_history[user_id] = []
                debate_preferences[user_id]['side'] = None
        
        # Set the new topic
        debate_preferences[user_id] = {'topic': topic, 'side': None}
        await send_message(update, f"You've chosen the topic: {topic}. Now choose your side using the /choose_side command (for or against).")
    
    except ValueError:
        await send_message(update, "Please specify the debate topic after the command. Example: /choose_topic Climate Change.")

async def choose_side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    message = update.message.text

    # Extract the side (for/against) from the message
    try:
        _, side = message.split(maxsplit=1)
        side = side.lower()
        if side not in ['for', 'against']:
            await send_message(update, "Please choose a valid side: 'for' or 'against'.")
            return

        # Check if the user has selected a topic
        if user_id not in debate_preferences or 'topic' not in debate_preferences[user_id]:
            await send_message(update, "You need to choose a debate topic first using /choose_topic.")
            return

        # If the user chooses a new side, clear the conversation history
        if debate_preferences[user_id]['side'] != side:
            conversation_history[user_id] = []

        # Set the new side for the user
        debate_preferences[user_id]['side'] = side
        await send_message(update, f"You've chosen to be {side} the topic '{debate_preferences[user_id]['topic']}'. You can now ask for help with your arguments.")
    
    except ValueError:
        await send_message(update, "Please specify your side (for/against) after the command. Example: /choose_side for.")

async def gpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    user_message = update.message.text

    # Check if the user has set a debate topic and side
    if user_id not in debate_preferences or debate_preferences[user_id]['side'] is None:
        await send_message(update, "Please choose a debate topic and side first using /choose_topic and /choose_side.")
        return

    debate_topic = debate_preferences[user_id]['topic']
    debate_side = debate_preferences[user_id]['side']

    # Check if the user is registered and verified
    user_record = get_user(user_id)
    if user_record is None:
        await send_message(update, "You are not registered. Please use the /register command to register first.")
        return

    is_verified = user_record[3]
    if not is_verified:
        await send_verification_prompt(update)
        return

    # Initialize conversation history if not present
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Add the user's message to the conversation history
    conversation_history[user_id].append({"role": "user", "content": user_message})

    # Use GPT to generate a reply, focused only on the debate topic
    prompt = f"You are helping a student prepare for a debate. The topic is '{debate_topic}', and the student is arguing {'for' if debate_side == 'for' else 'against'} it. Provide helpful advice, ideas, and counterarguments to support their position."

    # Add the prompt and conversation history
    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}] + conversation_history[user_id],
        stream=True,
    )

    response = ""
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            response += chunk.choices[0].delta.content

    # Add GPT's response to the conversation history
    conversation_history[user_id].append({"role": "assistant", "content": response})

    # Send the generated reply to the user
    await update.message.reply_text(response)

