import logging
import time
from config import Config
from assistant.meeting_preparation_assistant import MeetingPreparationAssistant
from exceptions.exceptions import MessagesNotFound
from googleapiclient.errors import HttpError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
config = Config()


def main():
    """Main function to run the Meeting Preparation Assistant."""
    try:
        logger.info("Starting Meeting Preparation Assistant")
        mpa = MeetingPreparationAssistant(config)
        while True:
            try:
                events = mpa.fetch_info_from_emails()
                for event_info in events.events_info:
                    modifications = mpa.modification_service.load_modifications()
                    task_list, modification = mpa.llm_service.generate_tasks(
                        event_info, modifications
                    )
                    mpa.send_tasklist(task_list)
                    if modification:
                        mpa.modification_service.save_modifications(modification)
                    mpa.gmail_service.add_label_to_message(
                        event_info.message_id, mpa.processed_label_id
                    )
            except MessagesNotFound:
                logger.info("No new messages found; waiting before retrying")
            except HttpError as error:
                logger.error(f"An HTTP error occurred: {error}")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                break

            logger.info(f"Waiting for {config.email_polling_retry_interval // 60} minutes before checking for new emails")
            time.sleep(config.email_polling_retry_interval)

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected.")
        time.sleep(0.5)
        print("Goodbye!")


if __name__ == "__main__":
    main()
