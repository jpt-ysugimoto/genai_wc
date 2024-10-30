import datetime
from pydantic import BaseModel, Field


class IsMeetingInvite(BaseModel):
    is_meeting_invite: bool = Field(
        default=False,
        description="A boolean indicating if the email content is a meeting invitation.",
    )


class EventInfo(BaseModel):
    message_id: str = Field(description="The ID of the email message.")
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
    att_contents: list = Field(
        default_factory=list,
        description="A list of dictionaries with attachment titles and summarized contents.",
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
