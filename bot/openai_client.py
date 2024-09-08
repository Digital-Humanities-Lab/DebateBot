from openai import OpenAI
from bot.config import load_config

# Load configuration
config = load_config()

# Initialize OpenAI client with the API key from config.txt
openai_client = OpenAI(api_key=config["OPENAI_API_KEY"])