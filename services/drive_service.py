import logging
import re
import io
from typing import Any
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from pypdf import PdfReader

logger = logging.getLogger(__name__)
Credentials = LLMService = Any


class DriveService:
    def __init__(self, creds: Credentials):
        """
        Initialize the Google Drive API service.

        Parameters
        ----------
        creds : Credentials
            OAuth2 credentials for Drive API access.
        """
        try:
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

            logger.info("Initialized Drive API service.")
        except HttpError as error:
            logger.error(f"Error initializing Drive service: {error}")
            raise Exception(f"An error occurred: {error}")

    def fetch_attachments(self, attachments: list, llm_service: LLMService):
        """
        Handle and process attachments from the event.

        Parameters
        ----------
        attachments : list
            A list of attachment URLs from the event.
        llm_service : LLMService
            An instance of LLMService.

        Returns
        -------
        list
            A list of dictionaries containing attachment titles and their summarized contents.
        """
        logger.info("Fetching and processing attachments")
        attachment_contents = []
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

            content = ""
            if mime_type == "application/vnd.google-apps.document":
                content = self.read_google_doc(file_id)
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                content = self.read_google_sheet(file_id)
            elif mime_type == "application/vnd.google-apps.presentation":
                content = self.read_google_slide(file_id)
            elif mime_type == "application/pdf":
                content = self.download_and_extract_pdf(file_id)
            elif mime_type in ["text/plain", "text/csv"]:
                content = self.download_file_as_text(file_id)
            else:
                content = "Unsupported file format."
                logger.warning(
                    f"Unsupported MIME type '{mime_type}' for attachment '{title}'"
                )
            if len(content) > 10**4:
                logger.info(
                    f"Content length for attachment '{title}' exceeds limit, truncating to 10,000 characters"
                )
                content = content[: 10**4]
            summarized_content = llm_service.summarize_with_llm(content)
            attachment_contents.append(
                {
                    "attachment_title": title,
                    "content": summarized_content,
                }
            )
            logger.info(f"Processed attachment '{title}'")
        return attachment_contents

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
