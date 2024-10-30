import logging
from icalendar import Calendar

from models.models import EventInfo

logger = logging.getLogger(__name__)


class EmailUtils:
    def __init__(self, drive_service, llm_service):
        """
        Initialize EmailUtils with required services.

        Parameters
        ----------
        drive_service : DriveService
            An instance of DriveService.
        llm_service : LLMService
            An instance of LLMService.
        docs_service : DocsService
            An instance of DocsService.
        sheets_service : SheetsService
            An instance of SheetsService.
        slides_service : SlidesService
            An instance of SlidesService.
        """
        self.drive_service = drive_service
        self.llm_service = llm_service

    def process_message(self, msg, gmail_service, processed_label_id):
        """
        Process a single message to determine if it is a meeting invite and extract event information.

        Parameters
        ----------
        msg : dict
            The message object from Gmail.
        gmail_service : GmailService
            An instance of GmailService.
        processed_label_id : str
            The ID of the 'Processed' label.

        Returns
        -------
        EventInfo or None
            Extracted EventInfo object if message is a meeting invite, otherwise None.
        """
        email_message = gmail_service.get_email_message(msg["id"])
        subject, body, ics_file_data = gmail_service.extract_email_parts(email_message)

        if ics_file_data and self.llm_service.is_meeting_invite(subject, body):
            logger.info(f"Email '{subject}' is identified as a meeting invitation")
            event_info = self.parse_ics_file(ics_file_data)
            event_info = event_info.copy(update={"message_id": msg["id"]})
            return event_info
        else:
            logger.info(f"Email '{subject}' is not a meeting invitation")
            return None

    def parse_ics_file(self, ics_data_bytes):
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
                message_id="",  # Placeholder; will be updated later
                event_title=event.get("SUMMARY"),
                description=event.get("DESCRIPTION", ""),
                start=event.get("DTSTART").dt,
                end=event.get("DTEND").dt,
                event_duration=event.get("DTEND").dt - event.get("DTSTART").dt,
                num_ppl=num_ppl,
                att_contents=(
                    self.drive_service.fetch_attachments(attachments, self.llm_service)
                    if attachments
                    else []
                ),
            )
            logger.info(f"Extracted event information: {event_info}")
            return event_info
