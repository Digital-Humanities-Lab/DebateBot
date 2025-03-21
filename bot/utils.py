import random
import json
import os

def generate_verification_code(length=6) -> str:
    """Generate a random numeric verification code."""
    return ''.join(random.choice('0123456789') for _ in range(length))

def load_messages(language):
    file_path = f"messages_{language}.json"
    if not os.path.exists(file_path):
        # Default to English if file doesn't exist
        file_path = "messages_en.json"
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)