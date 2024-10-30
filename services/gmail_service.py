import base64
import logging
import email
from email import message_from_bytes
from email.header import decode_header
from typing import Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)
Credentials = Any


class GmailService:
    def __init__(self, creds: Credentials, max_email_results: int, gmail_query: str):
        """
        Initialize the Gmail API service.

        Parameters
        ----------
        creds : Credentials
            OAuth2 credentials for Gmail API access.
        max_email_results : int
            Maximum number of emails to process at a time.
        gmail_query : str
            Query to find meeting invitations.
        """
        self.max_email_results = max_email_results
        self.gmail_query = gmail_query

        try:
            self.service = build(
                "gmail", "v1", credentials=creds, cache_discovery=False
            )
            logger.info("Initialized Gmail API service.")
        except HttpError as error:
            logger.error(f"Error initializing Gmail service: {error}")
            raise Exception(f"An error occurred: {error}")

    def get_or_create_label(self, label_name: str) -> str:
        """
        Retrieve the ID of the specified label. Create it if it doesn't exist.

        Parameters
        ----------
        label_name : str
            The name of the label.

        Returns
        -------
        str
            The ID of the label.
        """
        logger.info(f"Getting or creating label: {label_name}")
        try:
            labels = self.service.users().labels().list(userId="me").execute()
            for label in labels["labels"]:
                if label["name"] == label_name:
                    logger.info(f"Found label '{label_name}' with ID: {label['id']}")
                    return label["id"]

            label_body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            created_label = (
                self.service.users()
                .labels()
                .create(userId="me", body=label_body)
                .execute()
            )
            logger.info(f"Created label '{label_name}' with ID: {created_label['id']}")
            return created_label["id"]
        except HttpError as error:
            logger.error(f"Error getting or creating label '{label_name}': {error}")
            raise

    def add_label_to_message(self, message_id: str, label_id: str):
        """
        Add a label to a specific message.

        Parameters
        ----------
        message_id : str
            The ID of the message.
        label_id : str
            The ID of the label to add.
        """
        logger.info(f"Adding label ID '{label_id}' to message ID '{message_id}'")
        try:
            self.service.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": [label_id]}
            ).execute()
            logger.info(f"Added label ID '{label_id}' to message ID '{message_id}'")
        except HttpError as error:
            logger.error(f"Error adding label to message: {error}")
            raise

    def get_messages_with_ics_attachments(self):
        """
        Retrieve messages that contain .ics attachments.

        Returns
        -------
        list
            A list of message objects.
        """
        response = (
            self.service.users()
            .messages()
            .list(userId="me", q=self.gmail_query, maxResults=self.max_email_results)
            .execute()
        )
        return response.get("messages", [])

    def get_unprocessed_messages(self, messages: list, processed_label_id: str) -> list:
        """
        Filter messages to find those without the 'Processed' label.

        Parameters
        ----------
        messages : list
            A list of message objects.
        processed_label_id : str
            The ID of the 'Processed' label.

        Returns
        -------
        list
            A list of unprocessed message objects.
        """
        unprocessed_messages = []
        for msg in messages:
            msg_metadata = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata")
                .execute()
            )
            label_ids = msg_metadata.get("labelIds", [])
            if processed_label_id not in label_ids:
                unprocessed_messages.append(msg)
            else:
                logger.info(f"Message ID '{msg['id']}' already processed; skipping")
        return unprocessed_messages

    def get_email_message(self, message_id: str) -> email.message.Message:
        """
        Retrieve the full email message by ID.

        Parameters
        ----------
        message_id : str
            The ID of the email message.

        Returns
        -------
        email.message.Message
            The email message object.
        """
        msg_full = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        msg_bytes = base64.urlsafe_b64decode(msg_full["raw"])
        return message_from_bytes(msg_bytes)

    def extract_email_parts(self, email_message: email.message.Message) -> tuple:
        """
        Extract subject, body, and .ics file data from an email message.

        Parameters
        ----------
        email_message : email.message.Message
            The email message to extract from.

        Returns
        -------
        tuple
            Subject, body text, and .ics file data in bytes.
        """
        subject, encoding = decode_header(email_message["subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        body = ""
        ics_file_data = b""
        for part in email_message.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode("utf-8")
            elif "attachment" in content_disposition:
                file_name = part.get_filename()
                if file_name and file_name.endswith(".ics"):
                    ics_file_data = part.get_payload(decode=True)
                    logger.info(f"Found .ics attachment: {file_name}")
        return subject, body, ics_file_data
