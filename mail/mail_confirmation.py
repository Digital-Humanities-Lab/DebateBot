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

def load_email_template(file_path, verification_code):
    """Loads the email template from a file and replaces placeholders."""
    with open(file_path, 'r') as file:
        template = file.read()

    # Replace placeholders with actual values
    return template.replace('{{ verification_code }}', str(verification_code))

def send_email(recipient_email, verification_code):
    """Sends an email with a verification code using Gmail API and OAuth2 credentials."""
    creds = None
    token_path = "token.json"
    credentials_path = "credentials.json"  # Path to your OAuth2 credentials file
    template_path = "email_template.html"  # Path to your email template file

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
        # Load the HTML template and replace the placeholder
        html_body = load_email_template(template_path, verification_code)

        # Build the Gmail API service
        service = build('gmail', 'v1', credentials=creds)

        # Create the email content
        message = MIMEMultipart()
        message['From'] = email_from  # Use your verified email address
        message['To'] = recipient_email
        message['Subject'] = 'Your Verification Code'

        # Attach the body with the HTML content
        message.attach(MIMEText(html_body, 'html', 'utf-8'))

        # Encode the message in base64 and prepare it for sending
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        # Send the email using the Gmail API
        send_message = {
            'raw': raw_message
        }
        service.users().messages().send(userId="me", body=send_message).execute()

        # print(f"Verification email successfully sent to {recipient_email}")

    except HttpError as error:
        print(f"An error occurred: {error}")
        raise Exception(f"Failed to send email: {error}")