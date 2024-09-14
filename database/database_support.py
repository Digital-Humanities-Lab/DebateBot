import psycopg2
from psycopg2 import sql
from bot.config import load_config

config = load_config()

def get_db_connection():
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

# Create users table
def create_users_table():
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TYPE IF NOT EXISTS conversation_state_enum AS ENUM (
                    'STARTED', 'AWAITING_EMAIL', 'AWAITING_VERIFICATION_CODE', 'VERIFIED', 'AWAITING_DEBATE_TOPIC', 'AWAITING_DEBATE_SIDE', CHAT_GPT 
                );
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    email VARCHAR(255),
                    verification_code INT,
                    conversation_state conversation_state_enum NOT NULL,
                    topic VARCHAR(255),  -- To store the debate topic
                    side VARCHAR(50)     -- To store the user's chosen side (For/Against)
                );
            """)
            conn.commit()
    except Exception as e:
        print(f"Error creating table: {e}")
    finally:
        conn.close()

# Insert a new user
def insert_user(user_id, email, verification_code, conversation_state='STARTED', topic=None, side=None):
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

# Update the user's email and verification status
def update_user_email(user_id, new_email, verification_code):
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

# Update the user's verification status
def update_user_verification_status(user_id, verification_status):
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET conversation_state = %s
                WHERE user_id = %s;
            """, (verification_status, user_id))
            conn.commit()
    except Exception as e:
        print(f"Error updating verification status: {e}")
    finally:
        conn.close()

# Get the user's conversation state
def get_conversation_state(user_id):
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

# Get the user's email
def get_user_email(user_id):
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

# Check if the user exists
def user_exists(user_id):
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

# Get the verification code for the user
def get_verification_code(user_id):
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