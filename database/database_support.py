import firebase_admin
from firebase_admin import credentials, firestore
from bot.config import load_config

config = load_config()

cred = credentials.Certificate('firebase.json')
firebase_admin.initialize_app(cred)

db = firestore.client()

def insert_user(user_id, email, verification_code, conversation_state='STARTED', topic=None, side=None, language=None):
    """Insert a new user into Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.set({
            'email': email,
            'verification_code': verification_code,
            'conversation_state': conversation_state,
            'topic': topic,
            'side': side,
            'language': language  # Added language field
        }, merge=True)
    except Exception as e:
        print(f"Error inserting user: {e}")


def update_user_email(user_id, new_email, verification_code):
    """Update the user's email and verification code in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'email': new_email,
            'verification_code': verification_code,
            'conversation_state': 'AWAITING_VERIFICATION_CODE'
        })
    except Exception as e:
        print(f"Error updating email: {e}")


def update_user_conversation_state(user_id, conversation_state):
    """Update the user's conversation state in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'conversation_state': conversation_state
        })
    except Exception as e:
        print(f"Error updating conversation state: {e}")


def reset_user_registration(user_id):
    """Reset the user's registration data in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'email': firestore.DELETE_FIELD,
            'verification_code': firestore.DELETE_FIELD,
            'conversation_state': 'STARTED',
            # 'language': firestore.DELETE_FIELD,
        })
    except Exception as e:
        print(f"Error resetting user registration: {e}")


def get_conversation_state(user_id):
    """Get the user's conversation state from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('conversation_state')
        else:
            return None
    except Exception as e:
        print(f"Error fetching conversation state: {e}")
        return None


def update_user_language(user_id, language):
    """Update the user's language preference in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'language': language
        })
    except Exception as e:
        print(f"Error updating language: {e}")


def get_user_language(user_id):
    """Get the user's language preference from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('language', 'en')  # Default to 'en' if not set
        else:
            return 'en'
    except Exception as e:
        print(f"Error fetching user language: {e}")
        return 'en'
    

def get_user_email(user_id):
    """Get the user's email from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('email')
        else:
            return None
    except Exception as e:
        print(f"Error fetching user email: {e}")
        return None


def user_exists(user_id):
    """Check if the user exists in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        return user_ref.get().exists
    except Exception as e:
        print(f"Error checking if user exists: {e}")
        return False


def get_verification_code(user_id):
    """Get the verification code for the user from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('verification_code')
        else:
            return None
    except Exception as e:
        print(f"Error fetching verification code: {e}")
        return None


def update_user_debate_info(user_id, topic, side):
    """Update the user's debate topic and side in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'topic': topic,
            'side': side
        })
    except Exception as e:
        print(f"Error updating debate info: {e}")


def get_user_debate_info(user_id):
    """Get the user's debate topic and side from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return data.get('topic'), data.get('side')
        else:
            return None
    except Exception as e:
        print(f"Error fetching debate info: {e}")
        return None


def delete_user_from_db(user_id):
    """Delete a user from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.delete()
    except Exception as e:
        print(f"Error deleting user: {e}")