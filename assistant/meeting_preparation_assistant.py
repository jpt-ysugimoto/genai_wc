import os
import logging
from typing import Any
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from services.gmail_service import GmailService
from services.drive_service import DriveService
from services.llm_service import LLMService
from services.modification_service import ModificationService
from utils.email_utils import EmailUtils
from exceptions.exceptions import MessagesNotFound
from models.models import EventsInfo

logger = logging.getLogger(__name__)
Config = Any


class MeetingPreparationAssistant:
    def __init__(self, config: Config):
        """
        Initialize the MeetingPreparationAssistant by setting up credentials and API services.

        Parameters
        ----------
        config : Config
            Read each value stored in the config.yaml.
        """

        creds = None
        token_file = config.token_file
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(
                config.token_file, config.scopes
            )
            logger.info("Loaded credentials from token.json")
        else:
            logger.error(f"{token_file} not found")
            raise Exception("token.json not found")

        try:
            self.gmail_service = GmailService(
                creds, config.max_email_results, config.gmail_query
            )
            self.drive_service = DriveService(creds)
            self.llm_service = LLMService(
                config.model_name,
                config.max_iterations,
                config.modification_summary_threshold,
                config.task_generation_temperature,
            )
            self.modification_service = ModificationService(config.modifications_file)
            self.processed_label_id = self.gmail_service.get_or_create_label(
                config.processed_label_name
            )
            self.email_utils = EmailUtils(self.drive_service, self.llm_service)
        except HttpError as error:
            logger.error(f"An error occurred while initializing services: {error}")
            raise Exception(f"An error occurred: {error}")

    def fetch_info_from_emails(self) -> EventsInfo:
        """
        Fetch new emails from Gmail containing .ics files and extract event information.

        Returns
        -------
        EventsInfo
            An object containing information about events extracted from emails.

        Raises
        ------
        MessagesNotFound
            If no new meeting invitations are found.
        """
        messages = self.gmail_service.get_messages_with_ics_attachments()
        if not messages:
            logger.info("No new meeting invitations found")
            raise MessagesNotFound("No new meeting invitations found.")

        unprocessed_messages = self.gmail_service.get_unprocessed_messages(
            messages, self.processed_label_id
        )
        if not unprocessed_messages:
            logger.info("No unprocessed meeting invitations found")
            raise MessagesNotFound("No unprocessed meeting invitations found.")

        events_info = []
        for msg in unprocessed_messages:
            event_info = self.email_utils.process_message(
                msg, self.gmail_service, self.processed_label_id
            )
            if event_info:
                events_info.append(event_info)

        return EventsInfo(events_info=events_info)

    def send_tasklist(self, tasklist: dict):
        """
        Send the TaskList as an email to the user.

        Parameters
        ----------
        tasklist : dict
            The TaskList object containing tasks to be sent.
        """
        title = tasklist["title"]
        logger.info(f"Sending task list for event: {title}")
        body_text = f"Title: {title}\n\nTasks:\n"
        for task in tasklist["tasks"]:
            body_text += (
                f"""- Task: {task["task"]}\n"""
                f"""  Duration: {task["task_duration"]} minutes\n"""
                f"""  Note: {task["note"]}\n\n"""
            )

        message = self.create_message(f"Task List: {title}", body_text)
        self.send_email(message)
        logger.info(f"Task list sent for event: {title}")

    def create_message(self, subject: str, body_text: str) -> dict:
        """
        Create an email message.

        Parameters
        ----------
        subject : str
            The subject of the email.
        body_text : str
            The body text of the email.

        Returns
        -------
        dict
            The raw email message ready to be sent.
        """
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        message = MIMEMultipart()
        to = (
            self.gmail_service.service.users()
            .getProfile(userId="me")
            .execute()["emailAddress"]
        )
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body_text, "plain"))
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw_message}

    def send_email(self, message: dict) -> dict:
        """
        Send an email through the Gmail API.

        Parameters
        ----------
        message : dict
            The email message to be sent.

        Returns
        -------
        dict
            The sent message information.
        """
        logger.info("Sending email through Gmail API")
        message = (
            self.gmail_service.service.users()
            .messages()
            .send(userId="me", body=message)
            .execute()
        )
        logger.info(f"Email sent with Message Id: {message['id']}")
        return message
