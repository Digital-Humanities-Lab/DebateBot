import psycopg2
from psycopg2 import sql
from bot.config import load_config

# Load configuration (assume the config.txt includes database connection details)
config = load_config()

# Database connection
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

# Add a new user to the database
def add_user(user_id, email, verification_code, is_verified=False):
    conn = get_db_connection()
    if conn is None:
        return False
    
    try:
        with conn.cursor() as cursor:
            query = sql.SQL("INSERT INTO users (user_id, email, verification_code, is_verified) VALUES (%s, %s, %s, %s)")
            cursor.execute(query, (user_id, email, verification_code, is_verified))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding user: {e}")
        return False
    finally:
        conn.close()

# Get user by user_id
def get_user(user_id):
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        with conn.cursor() as cursor:
            query = sql.SQL("SELECT * FROM users WHERE user_id = %s")
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            return user
    except Exception as e:
        print(f"Error retrieving user: {e}")
        return None
    finally:
        conn.close()

# Update user's email
def update_user_email(user_id, new_email):
    conn = get_db_connection()
    if conn is None:
        return False
    
    try:
        with conn.cursor() as cursor:
            query = sql.SQL("UPDATE users SET email = %s WHERE user_id = %s")
            cursor.execute(query, (new_email, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating user email: {e}")
        return False
    finally:
        conn.close()

# Update user's verification status
def update_user_verification_status(user_id, is_verified):
    conn = get_db_connection()
    if conn is None:
        return False
    
    try:
        with conn.cursor() as cursor:
            query = sql.SQL("UPDATE users SET is_verified = %s WHERE user_id = %s")
            cursor.execute(query, (is_verified, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating user verification status: {e}")
        return False
    finally:
        conn.close()

# Set new verification code for a user
def set_verification_code(user_id, new_code):
    conn = get_db_connection()
    if conn is None:
        return False
    
    try:
        with conn.cursor() as cursor:
            query = sql.SQL("UPDATE users SET verification_code = %s WHERE user_id = %s")
            cursor.execute(query, (new_code, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error setting verification code: {e}")
        return False
    finally:
        conn.close()