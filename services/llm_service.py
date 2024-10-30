import logging

from langchain_community.chat_models import ChatDatabricks
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from models.models import IsMeetingInvite, TaskList
from dotenv import load_dotenv
import os

logger = logging.getLogger(__name__)

load_dotenv()
os.getenv("OPENAI_API_KEY")


class LLMService:
    def __init__(self, model_name):
        """
        Initialize the Language Model service.

        Parameters
        ----------
        model_name : str
            The name of the LLM model.
        """
        self.model_name = model_name

    def is_meeting_invite(self, subject, body):
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
        llm = ChatDatabricks(endpoint=self.model_name)
        chain = prompt | llm | parser
        result = chain.invoke(
            {
                "subject": subject,
                "body": body,
                "format_instructions": parser.get_format_instructions(),
            }
        )
        replaced_result = {
            key.replace("\\", ""): value for key, value in result.items()
        }
        is_invite = replaced_result["is_meeting_invite"]
        logger.info(f"LLM determined is_meeting_invite: {is_invite}")
        return is_invite

    def summarize_with_llm(self, content):
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
        llm = ChatDatabricks(endpoint=self.model_name, max_tokens=150)
        chain = prompt | llm
        summary = chain.invoke({"content": content}).content
        logger.info("Content summarized using LLM")
        return summary

    def summarize_modifications(self, modifications):
        """
        Summarize accumulated user feedback using LLM.

        Parameters
        ----------
        modifications : list
            A list of user modifications.

        Returns
        -------
        str
            The summarized modifications.
        """
        logger.info("Summarizing accumulated modifications.")

        llm = ChatDatabricks(endpoint=self.model_name, temperature=0.0)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful assistant that summarizes user feedback for improving task generation.",
                ),
                (
                    "human",
                    """
                    You have received the following user feedback to improve task generation:
                    {modifications}

                    Please provide a concise summary of the feedback to incorporate into the task generation instructions.
                    """,
                ),
            ]
        )
        chain = prompt | llm
        summarized_mod = chain.invoke({"modifications": modifications}).content
        logger.info("Successfully summarized modifications.")
        return summarized_mod

    def generate_tasks(self, event_info, modifications):
        """
        Generate a list of tasks required to prepare for a scheduled event with human feedback loop.

        Parameters
        ----------
        event_info : EventInfo
            An object containing detailed information about the event.
        modifications : list
            A list of user modifications.

        Returns
        -------
        dict
            A dictionary representing the TaskList.
        """
        logger.info(f"Generating tasks for event: {event_info.event_title}")
        title = event_info.event_title
        description = event_info.description
        event_duration = event_info.event_duration
        num_ppl = event_info.num_ppl
        att_contents = event_info.att_contents

        base_prompt = """
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
        """

        if len(modifications) >= 2:  # Adjust as needed
            summarized_mod = self.summarize_modifications(modifications)
            base_prompt += f"\n\n## Additional Instructions\n{summarized_mod}"
        parser = JsonOutputParser(pydantic_object=TaskList)

        max_iterations = 3
        iteration = 0
        modification = None
        while iteration < max_iterations:
            iteration += 1
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """
                    Review the meeting invitation email and create clear, actionable tasks based on the details.
                    Focus on tasks that help the recipient prepare for the meeting, like reviewing documents, understanding the agenda, or identifying key discussion points.
                    Ensure each task is directly related to the meeting content and easy to follow.
                    """,
                    ),
                    ("human", base_prompt),
                ]
            )
            llm = ChatDatabricks(endpoint=self.model_name, temperature=0.0)
            chain = prompt | llm | parser
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
            replaced_result = {
                key.replace("\\", ""): value for key, value in result.items()
            }
            print("Generated Tasks:")
            for i, task in enumerate(replaced_result["tasks"]):
                if i == 0:
                    print("=" * 100)
                print(f"""task title: {task["task"]}""")
                print(f"""task duration: {task["task_duration"]}""")
                print(f"""note: {task["note"]}""")
                print("=" * 100)

            feedback = (
                input(
                    f"Iteration {iteration}/{max_iterations}: Are you satisfied with the generated tasks? (yes/no): "
                )
                .strip()
                .lower()
            )
            if feedback == "yes":
                logger.info(f"User is satisfied with the tasks for event: {title}")
                break
            else:
                if iteration < max_iterations:
                    modification = input(
                        "Please provide your feedback to improve the tasks:\n"
                    )
                    base_prompt += f"\n\n## Additional Instructions\n{modification}"
                else:
                    logger.info(
                        "Maximum iterations reached. Proceeding with the latest tasks."
                    )
        logger.info(f"Generated tasks for event: {title}")
        return replaced_result, modification
