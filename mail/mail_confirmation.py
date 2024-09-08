import os
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bot.config import load_config

# Define the necessary scopes for sending emails
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

config = load_config()
email_from = config["EMAIL_FROM"]

def send_email(recipient_email, verification_code):
    """Sends an email with a verification code using Gmail API and OAuth2 credentials."""
    creds = None
    token_path = "token.json"
    credentials_path = "credentials.json"  # Path to your OAuth2 credentials file

    # Check if token.json exists, if not initiate OAuth2 flow
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If there are no valid credentials, ask user to log in and get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the new credentials to token.json for the next run
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())

    try:
        # Build the Gmail API service
        service = build('gmail', 'v1', credentials=creds)

        # Create the email content
        message = MIMEMultipart()
        message['From'] = email_from  # Use your verified email address
        message['To'] = recipient_email
        message['Subject'] = 'Your Verification Code'
        
        # Attach the body with the verification code
        body = f"Your verification code is: {verification_code}"
        message.attach(MIMEText(body, 'plain'))

        # Encode the message in base64 and prepare it for sending
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        # Send the email using the Gmail API
        send_message = {
            'raw': raw_message
        }
        service.users().messages().send(userId="me", body=send_message).execute()

    except HttpError as error:
        print(f"An error occurred: {error}")
