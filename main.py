import os
import base64
import io
import time
import re
import datetime
import logging
from icalendar import Calendar
from dotenv import load_dotenv
from pypdf import PdfReader
from pydantic import BaseModel, Field

from email import message_from_bytes
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IsMeetingInvite(BaseModel):
    is_meeting_invite: bool = Field(
        default=False,
        description="A boolean value indicating whether the email content is a meeting invitation.",
    )


class EventInfo(BaseModel):
    event_title: str = Field(description="The title of the event.")
    description: str = Field(description="A detailed description of the event.")
    start: datetime.datetime = Field(
        description="The start time of the event in ISO 8601 format."
    )
    end: datetime.datetime = Field(
        description="The end time of the event in ISO 8601 format."
    )
    event_duration: datetime.timedelta = Field(
        description="The duration of the event as a timedelta object."
    )
    num_ppl: int = Field(description="The number of participants in the event.")
    att_contents: list[dict[str, str]] = Field(
        default_factory=list,
        description="A list of dictionaries containing attachment titles and their summarized contents.",
    )


class EventsInfo(BaseModel):
    events_info: list[EventInfo] = Field(
        description="A list containing information about multiple events."
    )


class Task(BaseModel):
    task: str = Field(
        description="Represents the task required to prepare for a scheduled event."
    )
    task_duration: int = Field(description="The duration of the task in minutes.")
    note: str = Field(
        description="Important points to keep in mind when performing the task."
    )


class TaskList(BaseModel):
    title: str = Field(description="The title of the event.")
    tasks: list[Task] = Field(
        description="A list representing the tasks required to prepare for a scheduled event."
    )


class MessagesNotFound(Exception):
    """Exception raised when no new meeting invitations are found."""

    pass


class MeetingPreparationAssistant:
    def __init__(self):
        """
        Initialize the Google API Processor by setting up credentials and API services.

        Loads environment variables, sets up OAuth 2.0 credentials, and initializes services for Calendar, Gmail, Drive, Docs, Sheets, and Slides APIs.
        """
        load_dotenv()
        os.getenv("OPENAI_API_KEY")
        SCOPES = [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/documents.readonly",
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/presentations.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ]
        creds: Credentials | None = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            logger.info("Loaded credentials from token.json")
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                logger.info("Refreshed expired credentials")
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("Obtained new credentials via OAuth flow")
            with open("token.json", "w") as token:
                token.write(creds.to_json())
                logger.info("Saved credentials to token.json")
        try:
            self.calendar_service = build(
                "calendar", "v3", credentials=creds, cache_discovery=False
            )
            self.gmail_service = build(
                "gmail", "v1", credentials=creds, cache_discovery=False
            )
            self.drive_service = build(
                "drive", "v3", credentials=creds, cache_discovery=False
            )
            self.docs_service = build(
                "docs", "v1", credentials=creds, cache_discovery=False
            )
            self.sheets_service = build(
                "sheets", "v4", credentials=creds, cache_discovery=False
            )
            self.slides_service = build(
                "slides", "v1", credentials=creds, cache_discovery=False
            )
            logger.info("Initialized Google API services")
            # Get or create the 'Processed' label and store its ID
            self.processed_label_id = self.get_or_create_label("Processed")
        except HttpError as error:
            logger.error(
                f"An error occurred while initializing Google API services: {error}"
            )
            raise Exception(f"An error occurred: {error}")

    def get_or_create_label(self, label_name: str) -> str:
        """
        Retrieve the ID of the specified label. If it doesn't exist, create it.

        Parameters
        ----------
        label_name : str
            The name of the label to get or create.

        Returns
        -------
        str
            The ID of the label.
        """
        logger.info(f"Getting or creating label: {label_name}")
        try:
            # Get existing labels
            labels = self.gmail_service.users().labels().list(userId="me").execute()
            for label in labels["labels"]:
                if label["name"] == label_name:
                    logger.info(f"Label '{label_name}' found with ID: {label['id']}")
                    return label["id"]
            # Create the label if it doesn't exist
            label_body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            created_label = (
                self.gmail_service.users()
                .labels()
                .create(userId="me", body=label_body)
                .execute()
            )
            logger.info(f"Label '{label_name}' created with ID: {created_label['id']}")
            return created_label["id"]
        except HttpError as error:
            logger.error(
                f"An error occurred while getting or creating label '{label_name}': {error}"
            )
            raise

    def add_label_to_message(self, message_id: str, label_id: str):
        """
        Add a label to the specified message.

        Parameters
        ----------
        message_id : str
            The ID of the message to label.
        label_id : str
            The ID of the label to add.
        """
        logger.info(f"Adding label ID '{label_id}' to message ID '{message_id}'")
        try:
            self.gmail_service.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": [label_id]}
            ).execute()
            logger.info(f"Label ID '{label_id}' added to message ID '{message_id}'")
        except HttpError as error:
            logger.error(f"An error occurred while adding label to message: {error}")
            raise

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
        logger.info("Fetching new emails containing .ics files")
        messages = self.get_messages_with_ics_attachments()
        if not messages:
            logger.info("No new meeting invitations found")
            raise MessagesNotFound("No new meeting invitations found.")

        unprocessed_messages = self.get_unprocessed_messages(messages)
        if not unprocessed_messages:
            logger.info("No unprocessed meeting invitations found")
            raise MessagesNotFound("No unprocessed meeting invitations found.")

        events_info: list[EventInfo] = []

        for msg in unprocessed_messages:
            event_info = self.process_message(msg)
            if event_info:
                events_info.append(event_info)

        return EventsInfo(events_info=events_info)

    def get_messages_with_ics_attachments(self) -> list:
        query = "in:inbox has:attachment filename:ics"
        response = (
            self.gmail_service.users()
            .messages()
            .list(userId="me", q=query, maxResults=2)
            .execute()
        )
        return response.get("messages", [])

    def get_unprocessed_messages(self, messages: list) -> list:
        unprocessed_messages = []
        for msg in messages:
            msg_metadata = (
                self.gmail_service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata")
                .execute()
            )
            label_ids = msg_metadata.get("labelIds", [])
            if self.processed_label_id not in label_ids:
                unprocessed_messages.append(msg)
            else:
                logger.info(f"Message ID '{msg['id']}' already processed; skipping")
        return unprocessed_messages

    def process_message(self, msg: dict) -> EventInfo:
        email_message = self.get_email_message(msg["id"])
        subject, body, ics_file_data = self.extract_email_parts(email_message)

        if ics_file_data and self.is_meeting_invite(subject, body):
            logger.info(f"Email '{subject}' is identified as a meeting invitation")
            event_info = self.parse_ics_file(ics_file_data)
            self.add_label_to_message(msg["id"], self.processed_label_id)
            return event_info
        else:
            logger.info(f"Email '{subject}' is not a meeting invitation")
            return None

    def get_email_message(self, message_id: str):
        msg_full = (
            self.gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        msg_bytes = base64.urlsafe_b64decode(msg_full["raw"])
        return message_from_bytes(msg_bytes)

    def extract_email_parts(self, email_message) -> tuple:
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

    def is_meeting_invite(self, subject: str, body: str) -> bool:
        """
        Use LLM to determine if the email is a meeting invite.

        Parameters
        ----------
        subject : str
            The subject line of the email.
        body : str
            The body content of the email.

        Returns
        -------
        bool
            True if the email is a meeting invitation, False otherwise.
        """
        logger.info("Determining if email is a meeting invitation using LLM")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a helpful assistant."),
                (
                    "human",
                    """
                    ## Instruction
                    Is the following email content a meeting invitation?

                    ## Email content
                    Subject: {subject}
                    Body: {body}

                    ## Answer construction
                    Answer {format_instructions}
                    """,
                ),
            ]
        )
        parser = JsonOutputParser(pydantic_object=IsMeetingInvite)
        llm = ChatOpenAI(model="gpt-4o-mini")
        chain = prompt | llm | parser
        result = chain.invoke(
            {
                "subject": subject,
                "body": body,
                "format_instructions": parser.get_format_instructions(),
            }
        )
        is_invite = result["is_meeting_invite"]
        logger.info(f"LLM determined is_meeting_invite: {is_invite}")
        return is_invite

    def parse_ics_file(self, ics_data_bytes: bytes) -> EventInfo:
        """
        Parse the .ics file from the email and extract event information.

        Parameters
        ----------
        ics_data_bytes : bytes
            The raw bytes of the .ics file.

        Returns
        -------
        EventInfo
            An object containing detailed information about the event.
        """
        logger.info("Parsing .ics file to extract event information")
        ics_data_text = ics_data_bytes.decode("utf-8")
        calendar = Calendar.from_ical(ics_data_text)

        for event in calendar.walk("VEVENT"):
            attachments = (
                [event.get("ATTACH")]
                if isinstance(event.get("ATTACH"), str)
                else event.get("ATTACH")
            )
            attendees = event.get("ATTENDEE")
            if isinstance(attendees, list):
                num_ppl = len(attendees)
            else:
                num_ppl = 1 if attendees else 0
            event_info = EventInfo(
                event_title=event.get("SUMMARY"),
                description=event.get("DESCRIPTION", ""),
                start=event.get("DTSTART").dt,
                end=event.get("DTEND").dt,
                event_duration=event.get("DTEND").dt - event.get("DTSTART").dt,
                num_ppl=num_ppl,
                att_contents=self.fetch_attachments(attachments) if attachments else [],
            )
            logger.info(f"Extracted event information: {event_info}")
            return event_info

    def fetch_attachments(self, attachments: list) -> list[dict[str, str]]:
        """
        Handle and process attachments from the event.

        Parameters
        ----------
        attachments : list
            A list of attachment URLs from the event.

        Returns
        -------
        list of dict
            A list of dictionaries containing the attachment title and summarized content.
        """
        logger.info("Fetching and processing attachments")
        attachment_contents: list[dict[str, str]] = []
        for attachment in attachments:
            file_id = self.extract_file_id(attachment)
            if not file_id:
                logger.warning(
                    f"Could not extract file ID from attachment URL: {attachment}"
                )
                continue
            logger.info(f"Processing attachment with file ID: {file_id}")
            meta_data = self.get_file_metadata(file_id)
            title = meta_data.get("name")
            mime_type = meta_data.get("mimeType")
            logger.info(f"Attachment '{title}' has MIME type '{mime_type}'")

            # Get the content of the file
            content = ""
            if mime_type == "application/vnd.google-apps.document":
                content = self.read_google_doc(file_id)
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                content = self.read_google_sheet(file_id)
            elif mime_type == "application/vnd.google-apps.presentation":
                content = self.read_google_slide(file_id)
            elif mime_type == "application/pdf":
                content = self.download_and_extract_pdf(file_id)
            elif mime_type == "text/plain":
                content = self.download_file_as_text(file_id)
            elif mime_type == "text/csv":
                content = self.download_file_as_text(file_id)
            else:
                content = "Unsupported file format."
                logger.warning(
                    f"Unsupported MIME type '{mime_type}' for attachment '{title}'"
                )

            summarized_content = self.summarize_with_llm(content)
            attachment_contents.append(
                {
                    "attachment_title": title,
                    "content": summarized_content,
                }
            )
            logger.info(f"Processed attachment '{title}'")
        return attachment_contents

    def get_file_metadata(self, file_id: str) -> dict:
        """
        Retrieve metadata for a file in Google Drive.

        Parameters
        ----------
        file_id : str
            The ID of the file.

        Returns
        -------
        dict
            Metadata of the file.
        """
        logger.info(f"Fetching metadata for file ID: {file_id}")
        return self.drive_service.files().get(fileId=file_id).execute()

    def extract_file_id(self, url: str) -> str | None:
        """
        Extract the file ID from a Google Drive URL.

        Parameters
        ----------
        url : str
            The URL containing the file ID.

        Returns
        -------
        str or None
            The extracted file ID, or None if not found.
        """
        match = re.search(r"id=([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        else:
            logger.warning(f"Failed to extract file ID from URL: {url}")
            return None

    def read_google_doc(self, file_id: str) -> str:
        """
        Extract text content from a Google Doc.

        Parameters
        ----------
        file_id : str
            The ID of the Google Doc file.

        Returns
        -------
        str
            The text content extracted from the Google Doc.
        """
        logger.info(f"Reading Google Doc with file ID: {file_id}")
        text = ""
        doc = self.docs_service.documents().get(documentId=file_id).execute()
        for content in doc.get("body", {}).get("content", []):
            paragraph = content.get("paragraph")
            if paragraph:
                elements = paragraph.get("elements", [])
                for element in elements:
                    text_run = element.get("textRun")
                    if text_run:
                        text += text_run.get("content", "")
        return text

    def read_google_sheet(self, file_id: str) -> str:
        """
        Retrieve text content from a Google Sheet.

        Parameters
        ----------
        file_id : str
            The ID of the Google Sheet file.

        Returns
        -------
        str
            The text content extracted from the Google Sheet.
        """
        logger.info(f"Reading Google Sheet with file ID: {file_id}")
        sheet = self.sheets_service.spreadsheets()
        result = sheet.values().get(spreadsheetId=file_id, range="A1:Z1000").execute()
        values = result.get("values", [])
        text = ""
        for row in values:
            text += ", ".join(row) + "\n"
        return text

    def read_google_slide(self, file_id: str) -> str:
        """
        Retrieve text content from a Google Slide presentation.

        Parameters
        ----------
        file_id : str
            The ID of the Google Slide file.

        Returns
        -------
        str
            The text content extracted from the Google Slides presentation.
        """
        logger.info(f"Reading Google Slides presentation with file ID: {file_id}")
        presentation = (
            self.slides_service.presentations().get(presentationId=file_id).execute()
        )
        slides = presentation.get("slides", [])
        text = ""
        for slide in slides:
            for element in slide.get("pageElements", []):
                shape = element.get("shape")
                if shape:
                    text_elements = shape.get("text", {}).get("textElements", [])
                    for text_element in text_elements:
                        text_run = text_element.get("textRun")
                        if text_run:
                            content = text_run.get("content", "")
                            if content:
                                text += content
        return text

    def download_and_extract_pdf(self, file_id: str) -> str:
        """
        Download a PDF file and extract text from it.

        Parameters
        ----------
        file_id : str
            The ID of the PDF file.

        Returns
        -------
        str
            The text content extracted from the PDF.
        """
        logger.info(f"Downloading and extracting PDF with file ID: {file_id}")
        request = self.drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            logger.debug(f"Download progress: {int(status.progress() * 100)}%")
        fh.seek(0)
        reader = PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text

    def download_file_as_text(self, file_id: str) -> str:
        """
        Download a text or CSV file and return its content.

        Parameters
        ----------
        file_id : str
            The ID of the text or CSV file.

        Returns
        -------
        str
            The text content of the file.
        """
        logger.info(f"Downloading file as text with file ID: {file_id}")
        request = self.drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            logger.debug(f"Download progress: {int(status.progress() * 100)}%")
        fh.seek(0)
        text = fh.read().decode("utf-8")
        return text

    def summarize_with_llm(self, content: str) -> str:
        """
        Use LLM to summarize the given content.

        Parameters
        ----------
        content : str
            The text content to be summarized.

        Returns
        -------
        str
            The summarized text.
        """
        logger.info("Summarizing content using LLM")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a summarization assistant."),
                ("human", "Please summarize the following text: {content}"),
            ]
        )
        llm = ChatOpenAI(model="gpt-4o-mini", max_tokens=150)
        chain = prompt | llm
        summary = chain.invoke({"content": content}).content
        logger.info("Content summarized using LLM")
        return summary

    def generate_tasks(self, event_info: EventInfo) -> TaskList:
        """
        Generate a list of tasks required to prepare for a scheduled event.

        Parameters
        ----------
        event_info : EventInfo
            An object containing detailed information about the event.

        Returns
        -------
        TaskList
            A list of tasks with details such as duration and notes.
        """
        logger.info(f"Generating tasks for event: {event_info.event_title}")
        title = event_info.event_title
        description = event_info.description
        event_duration = event_info.event_duration
        num_ppl = event_info.num_ppl
        att_contents = event_info.att_contents

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful assistant.",
                ),
                (
                    "human",
                    """
                    ## Event Details
                    Event Summary: {title}
                    Description: {description}
                    Meeting Duration (hours): {event_duration}
                    Number of Participants: {num_ppl}
                    Summaries of Attachments: {att_contents}

                    ## Instructions
                    Based on the above event details, please propose:
                    - Tasks that should be completed before the event starts
                    - The duration required for each task
                    - Points to keep in mind for each task

                    ## Output Format
                    {format_instructions}
                    """,
                ),
            ]
        )
        parser = JsonOutputParser(pydantic_object=TaskList)

        model = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
        chain = prompt | model | parser
        result = chain.invoke(
            {
                "title": title,
                "description": description,
                "event_duration": event_duration,
                "num_ppl": num_ppl,
                "att_contents": att_contents,
                "format_instructions": parser.get_format_instructions(),
            }
        )
        logger.info(f"Generated tasks for event: {title}")
        return result

    def send_tasklist(self, tasklist: TaskList):
        """
        Send the TaskList as an email to the user.

        Parameters
        ----------
        tasklist : TaskList
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
        logger.info(f"Creating email message with subject: {subject}")
        message = MIMEMultipart()
        to = (
            self.gmail_service.users().getProfile(userId="me").execute()["emailAddress"]
        )
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body_text, "plain"))
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw_message}

    def send_email(self, message: dict):
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
            self.gmail_service.users()
            .messages()
            .send(userId="me", body=message)
            .execute()
        )
        logger.info(f"Email sent with Message Id: {message['id']}")
        return message


def main():
    """Main function to run the Google API Processor."""
    try:
        logger.info("Starting Google API Processor")
        mpa = MeetingPreparationAssistant()
        while True:
            try:
                events = mpa.fetch_info_from_emails()
                for event_info in events.events_info:
                    task_list = mpa.generate_tasks(event_info)
                    mpa.send_tasklist(task_list)
            except MessagesNotFound:
                logger.info("No new messages found; waiting before retrying")
            except HttpError as error:
                logger.error(f"An HTTP error occurred: {error}")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                break

            # Wait for 5 minutes before polling again
            time.sleep(30)
            logger.info("Waiting for 5 minutes before checking for new emails")
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected.")
        time.sleep(0.5)
        print("Goodbye!")


if __name__ == "__main__":
    main()
