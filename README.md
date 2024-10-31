# Meeting Preparation Assistant

**Important:** The `token.json` file is required for authentication with Google APIs. Make sure to generate and include this file in your project directory before running the script.

The Meeting Preparation Assistant is a Python script that automates your meeting preparation by:

- Scanning your Gmail inbox for new meeting invitations with `.ics` attachments.
- Extracting event details and summarizing attachments using a Large Language Model (LLM).
- Generating a customized list of tasks to help you prepare for the meeting.
- **Incorporating your feedback to improve future task generation.**
- Sending the task list to you via email and labeling processed emails.

---

## Table of Contents

- [Meeting Preparation Assistant](#meeting-preparation-assistant)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Setup Instructions](#setup-instructions)
  - [Follow the link in the terminal to complete the authorization. Afterward, `token.json` will appear in your project directory.](#follow-the-link-in-the-terminal-to-complete-the-authorization-afterward-tokenjson-will-appear-in-your-project-directory)
  - [Running the Script](#running-the-script)
  - [How It Works](#how-it-works)
  - [Interactive Feedback Loop](#interactive-feedback-loop)
    - [Key Feature: Your Feedback Improves Future Tasks](#key-feature-your-feedback-improves-future-tasks)
  - [Configuration](#configuration)
    - [YAML Configuration File](#yaml-configuration-file)
    - [Configuration Variables](#configuration-variables)
  - [Folder Struction](#folder-struction)

---

## Prerequisites

- **Python 3.8 or higher**
- **Google account** with Gmail, Google Calendar, Drive, Docs, Sheets, and Slides access.
- **Google API credentials** (`credentials.json` and `token.json` files).
- **Databricks LLM endpoint** for language processing tasks.

---

## Setup Instructions

1. **Clone the Repository**

   ```bash
   git clone https://github.com/yourusername/meeting-preparation-assistant.git
   cd meeting-preparation-assistant
   ```

2. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Obtain `credentials.json`** 
   To generate `credentials.json`, please follow the instructions in the [Google Cloud guide on creating and managing service account keys](https://cloud.google.com/iam/docs/keys-create-delete).

4. **Generate `token.json`**
   To create the `token.json` file, run the following script to perform an initial authorization for Gmail:

   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow
   from googleapiclient.discovery import build

   SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

   def generate_token():
      flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
      creds = flow.run_local_server(port=0)
      with open('token.json', 'w') as token:
         token.write(creds.to_json())

   generate_token()
   ```

   Run this script from the command line:

   ```bash
   python generate_token.py
   ```

   Follow the link in the terminal to complete the authorization. Afterward, `token.json` will appear in your project directory.
---

## Running the Script

Run the script using:

```bash
python main.py
```

The script will check for new emails every 5 minutes. Press `Ctrl+C` to stop.

---

## How It Works

1. **Email Scanning**

   - Searches your Gmail inbox for new meeting invitations with `.ics` attachments.

2. **Event Information Extraction**

   - Parses the `.ics` file to extract event details.

3. **Attachment Summarization**

   - Downloads and summarizes attachments using the LLM.

4. **Task Generation**

   - Generates a list of preparatory tasks for the meeting.

5. **Email Notification**

   - Sends the task list to your email.

6. **Email Labeling**

   - Labels processed emails to prevent duplication.

---

## Interactive Feedback Loop

### Key Feature: Your Feedback Improves Future Tasks

After generating the tasks, the script engages you in an interactive loop to refine and enhance task generation:

1. **Task Presentation**

   - The generated tasks are displayed in the console for your review.

2. **Feedback Collection**

   - You're prompted to indicate if you're satisfied with the tasks:
     - **Yes:** Accept the tasks as they are.
     - **No:** Provide feedback for improvement.

3. **Task Regeneration**

   - Your input is stored and used to improve the prompt.
   - The script regenerates the tasks based on your feedback.
   - This loop can occur up to 3 times per task list.

4. **Prompt Improvement**

   - Once enough feedback is collected, the script summarizes it using the LLM.
   - The summarized feedback enhances future task generation, making it more aligned with your preferences.

---
## Configuration

### YAML Configuration File

The script uses a `config.yaml` file to manage constants and settings, making it easy to customize the behavior without modifying the code.

### Configuration Variables

The script uses a `config.yaml` file for configuration. Below are explanations of each variable:

- **model_name**: *(str)* The endpoint or name of the Large Language Model (LLM) to be used.
- **task_generation_temperature**: *(float)* Control the LLM that generates tasks. A value between 0.0 (deterministic) and 1.0 (more random).
- **scopes**: *(list)* A list of Google API scopes required for the application.
- **token_file**: *(str)* The filename where the OAuth 2.0 token is stored.
- **modifications_file**: *(str)* The filename for storing user feedback modifications.
- **processed_label_name**: *(str)* The name of the Gmail label used to mark processed emails.
- **gmail_query**: *(str)* The query string used to search for relevant emails in Gmail.
- **max_email_results**: *(int)* The maximum number of emails to process at once.
- **max_iterations**: *(int)* The maximum number of feedback loops for task generation.
- **modification_summary_threshold**: *(int)* The number of feedback entries required before summarizing modifications.
- **email_polling_retry_interval**: *(int)* The interval (in seconds) between email checks.

---

## Folder Struction

