import psycopg2
from psycopg2 import sql
from bot.config import load_config

config = load_config()


def get_db_connection():
    """Get a connection to the database."""
    try:
        conn = psycopg2.connect(
            dbname=config["DB_NAME"],
            user=config["DB_USER"],
            password=config["DB_PASSWORD"],
            host=config["DB_HOST"],
            port=config["DB_PORT"]
        )
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None


def create_users_table():
    """Create the users table in the database."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TYPE IF NOT EXISTS conversation_state_enum AS ENUM (
                    'STARTED', 'AWAITING_EMAIL', 'AWAITING_VERIFICATION_CODE', 'VERIFIED', 'AWAITING_DEBATE_TOPIC', 'AWAITING_DEBATE_SIDE', 'CHAT_GPT' 
                );
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    email VARCHAR(255),
                    verification_code INT,
                    conversation_state conversation_state_enum NOT NULL,
                    topic VARCHAR(255),
                    side VARCHAR(50)
                );
            """)
            conn.commit()
    except Exception as e:
        print(f"Error creating table: {e}")
    finally:
        conn.close()


def insert_user(user_id, email, verification_code, conversation_state='STARTED', topic=None, side=None):
    """Insert a new user into the database."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, email, verification_code, conversation_state, topic, side)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING;
            """, (user_id, email, verification_code, conversation_state, topic, side))
            conn.commit()
    except Exception as e:
        print(f"Error inserting user: {e}")
    finally:
        conn.close()


def update_user_email(user_id, new_email, verification_code):
    """Update the user's email and verification code."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET email = %s, verification_code = %s, conversation_state = 'AWAITING_VERIFICATION_CODE'
                WHERE user_id = %s;
            """, (new_email, verification_code, user_id))
            conn.commit()
    except Exception as e:
        print(f"Error updating email: {e}")
    finally:
        conn.close()


def update_user_conversation_state(user_id, conversation_state):
    """Update the user's conversation state."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET conversation_state = %s
                WHERE user_id = %s;
            """, (conversation_state, user_id))
            conn.commit()
    except Exception as e:
        print(f"Error updating conversation state: {e}")
    finally:
        conn.close()


def reset_user_registration(user_id):
    """Reset the user's registration data."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET email = NULL, verification_code = NULL, conversation_state = 'STARTED'
                WHERE user_id = %s;
            """, (user_id,))
            conn.commit()
    except Exception as e:
        print(f"Error resetting user registration: {e}")
    finally:
        conn.close()


def get_conversation_state(user_id):
    """Get the user's conversation state."""
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT conversation_state FROM users WHERE user_id = %s;
            """, (user_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Error fetching conversation state: {e}")
        return None
    finally:
        conn.close()


def get_user_email(user_id):
    """Get the user's email."""
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT email FROM users WHERE user_id = %s;
            """, (user_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Error fetching user email: {e}")
        return None
    finally:
        conn.close()


def user_exists(user_id):
    """Check if the user exists."""
    conn = get_db_connection()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS(SELECT 1 FROM users WHERE user_id = %s);
            """, (user_id,))
            result = cur.fetchone()
            return result[0] if result else False
    except Exception as e:
        print(f"Error checking if user exists: {e}")
        return False
    finally:
        conn.close()


def get_verification_code(user_id):
    """Get the verification code for the user."""
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT verification_code FROM users WHERE user_id = %s;
            """, (user_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Error fetching verification code: {e}")
        return None
    finally:
        conn.close()


def update_user_debate_info(user_id, topic, side):
    """Update the user's debate topic and side."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET topic = %s, side = %s
                WHERE user_id = %s;
            """, (topic, side, user_id))
            conn.commit()
    except Exception as e:
        print(f"Error updating debate info: {e}")
    finally:
        conn.close()


def get_user_debate_info(user_id):
    """Get the user's debate topic and side."""
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT topic, side FROM users WHERE user_id = %s;
            """, (user_id,))
            result = cur.fetchone()
            return result if result else None
    except Exception as e:
        print(f"Error fetching debate info: {e}")
        return None
    finally:
        conn.close()

def delete_user_from_db(user_id):
    """Delete a user from the database."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM users WHERE user_id = %s;
            """, (user_id,))
            conn.commit()
    except Exception as e:
        print(f"Error deleting user: {e}")
    finally:
        conn.close()