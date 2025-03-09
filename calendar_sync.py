#!/usr/bin/env python3
"""
Calendar to ClickUp Sync

This script retrieves upcoming events from Google Calendar for specified users
and creates corresponding tasks in ClickUp for capacity planning.
"""

import calendar
import datetime
import logging
import re
import sys
from html.parser import HTMLParser

import requests
from config import (
    CALENDAR_SYNC_DAYS,
    CLICKUP_API_KEY,
    CLICKUP_LIST_ID,
    CLICKUP_TEAM_ID,
    DATE_FORMAT,
    DATE_FORMAT_NO_TIME,
    DEBUG,
    GOOGLE_CALENDAR_SCOPES,
    HOST_DOMAINS,
    HOST_EMAILS,
    LOG_FILE,
    SERVICE_ACCOUNT_FILE,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

__version__ = "0.1.0"


# Set up logging
def setup_logging():
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(levelname)-7s - %(filename)s:%(funcName)s:%(lineno)d - %(message)s"
    log_level = logging.DEBUG if DEBUG else logging.INFO

    logging.basicConfig(filename=LOG_FILE, format=log_format, level=log_level)

    # Add console handler for visibility
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(log_format))
    logging.getLogger("").addHandler(console)

    # Handle uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    return logging.getLogger(__name__)


logger = setup_logging()


class HTMLtoTextConverter(HTMLParser):
    """Convert HTML to plain text while preserving structure."""

    def __init__(self):
        super().__init__()
        self.result = []
        self.list_item_prefix = ""
        self.in_list = False
        self.list_item_num = 0
        self.skip_data = False
        self.in_link = False
        self.link_href = ""

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.result.append("\n")
        elif tag == "p":
            if self.result and not self.result[-1].endswith("\n"):
                self.result.append("\n")
        elif tag == "ul":
            self.in_list = True
            self.list_item_prefix = "• "
            self.result.append("\n")
        elif tag == "ol":
            self.in_list = True
            self.list_item_prefix = "1. "
            self.list_item_num = 1
            self.result.append("\n")
        elif tag == "li":
            if self.in_list:
                prefix = self.list_item_prefix
                if prefix == "1. ":
                    prefix = f"{self.list_item_num}. "
                    self.list_item_num += 1
                self.result.append(f"\n{prefix}")
        elif tag == "a":
            self.in_link = True
            for attr in attrs:
                if attr[0] == "href":
                    self.link_href = attr[1]
        elif tag in ["script", "style"]:
            self.skip_data = True

    def handle_endtag(self, tag):
        if tag == "p":
            self.result.append("\n")
        elif tag in ["ul", "ol"]:
            self.in_list = False
            self.result.append("\n")
        elif tag == "a":
            if self.in_link and self.link_href:
                self.result.append(f" ({self.link_href})")
            self.in_link = False
            self.link_href = ""
        elif tag in ["script", "style"]:
            self.skip_data = False

    def handle_data(self, data):
        if not self.skip_data:
            self.result.append(data)

    def get_text(self):
        return "".join(self.result)


def clean_html(html_text):
    """Convert HTML to plain text, preserving structure."""
    if not html_text:
        return ""

    # Replace common problematic HTML entities
    html_text = html_text.replace("&nbsp;", " ")

    # Remove excessive whitespace
    html_text = re.sub(r"\s+", " ", html_text)

    # Parse HTML
    converter = HTMLtoTextConverter()
    converter.feed(html_text)
    text = converter.get_text()

    # Clean up extra newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class GoogleCalendarService:
    """Service for fetching Google Calendar events."""

    def __init__(self, service_account_file, scopes):
        """
        Initialize the Google Calendar service.

        Args:
            service_account_file (str): Path to the service account credentials file
            scopes (list): List of API scopes
        """
        self.service_account_file = service_account_file
        self.scopes = scopes

    def get_credentials(self, user_email):
        """
        Get credentials for the specified user.

        Args:
            user_email (str): Email of the user to impersonate

        Returns:
            Credentials: Google service account credentials
        """
        return service_account.Credentials.from_service_account_file(
            self.service_account_file, scopes=self.scopes, subject=user_email
        )

    def get_calendar_service(self, user_email):
        """
        Build a Google Calendar service for the specified user.

        Args:
            user_email (str): Email of the user

        Returns:
            Service: Google Calendar service
        """
        credentials = self.get_credentials(user_email)
        return build("calendar", "v3", credentials=credentials)

    def get_calendar_events(self, user_email, days_ahead=14):
        """
        Fetch calendar events for a user.

        Args:
            user_email (str): Email of the user
            days_ahead (int): Number of days to look ahead for events

        Returns:
            list: List of calendar events
        """
        logger.debug(f"Getting events for {user_email}...")

        try:
            service = self.get_calendar_service(user_email)

            # Calculate time range
            now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
            later = (datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)).isoformat() + "Z"

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    timeMax=later,
                    maxResults=100,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            return events_result.get("items", [])

        except HttpError as error:
            logger.exception(f"Error retrieving calendar for {user_email}: {error}")
            return []

    def get_all_calendar_events(self, user_emails, days_ahead=14):
        """
        Fetch calendar events for multiple users.

        Args:
            user_emails (list): List of user emails
            days_ahead (int): Number of days to look ahead for events

        Returns:
            list: Combined list of calendar events
        """
        all_events = []

        for email in user_emails:
            events = self.get_calendar_events(email, days_ahead)
            all_events.extend(events)

        logger.debug(f"Total events retrieved: {len(all_events)}")
        return all_events


class EventProcessor:
    """Process and filter calendar events."""

    def process_events(self, events):
        """
        Process and deduplicate calendar events.

        Args:
            events (list): Raw calendar events

        Returns:
            dict: Deduplicated and processed events
        """
        processed_events = {}

        logger.debug(f"Processing {len(events)} events...")

        for event in events:
            # Skip events without summary
            if "summary" not in event:
                logger.debug("No summary. Skipping event...")
                continue

            # Skip events without attendees
            if "attendees" not in event:
                logger.debug(f"No attendees. Skipping event: '{event['summary']}'...")
                continue

            # Extract start and end times
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))

            # Calculate duration
            duration = None
            try:
                duration = datetime.datetime.strptime(end, DATE_FORMAT) - datetime.datetime.strptime(start, DATE_FORMAT)
            except ValueError:
                logger.debug(f"Failed date format: {event['summary']} (start={start}, end={end})")

                # Try all-day event format
                try:
                    duration = datetime.datetime.strptime(end, DATE_FORMAT_NO_TIME) - datetime.datetime.strptime(
                        start, DATE_FORMAT_NO_TIME
                    )
                    logger.debug(f"No time on event. Skipping event: '{event['summary']}'...")
                    continue
                except ValueError:
                    logger.error(
                        f"Failed date format for all day: {event['summary']} (start={start}, end={end}). Skipping..."
                    )
                    continue

            if duration is None:
                logger.error(f"Failed date format import: {event['summary']} (start={start}, end={end}). Skipping...")
                continue

            # Extract additional valuable information
            description = event.get("description", "")
            location = event.get("location", "")
            status = event.get("status", "confirmed")

            # Fix: Check multiple indicators for recurring events
            is_recurring = (
                "recurrence" in event
                or "recurringEventId" in event
                or (event.get("description", "") and "recurring series" in event.get("description", "").lower())
            )

            if is_recurring:
                logger.debug(f"Recurring meeting detected: {event.get('summary')}")
                if "recurrence" in event:
                    logger.debug("  - Has recurrence field")
                if "recurringEventId" in event:
                    logger.debug(f"  - Has recurringEventId field: {event.get('recurringEventId')}")
                if event.get("description", "") and "recurring series" in event.get("description", "").lower():
                    logger.debug("  - Description contains 'recurring series'")

            organizer = event.get("organizer", {}).get("email", "")

            # Extract conference data if available
            conference_data = event.get("conferenceData", {})
            meeting_link = ""
            if conference_data and "entryPoints" in conference_data:
                for entry_point in conference_data["entryPoints"]:
                    if entry_point.get("entryPointType") in ["video", "more"]:
                        meeting_link = entry_point.get("uri", "")
                        break

            # Create simplified event object with additional fields
            processed_event = {
                "summary": event["summary"],
                "attendees": event["attendees"],
                "start": datetime.datetime.strptime(start, DATE_FORMAT),
                "end": datetime.datetime.strptime(end, DATE_FORMAT),
                "duration": duration,
                "iCalUID": event["iCalUID"],
                "description": description,
                "location": location,
                "meeting_link": meeting_link,
                "status": status,
                "is_recurring": is_recurring,
                "organizer": organizer,
                "recurrence": event.get("recurrence", []),  # Store recurrence rules if available
                "recurringEventId": event.get("recurringEventId", ""),  # Store recurring event ID if available
            }

            # Use UID as key to deduplicate
            processed_events[event["iCalUID"]] = processed_event

        logger.debug(f"Processed {len(processed_events)} unique events")
        return processed_events


class ClickUpService:
    """Service for interacting with ClickUp API."""

    def __init__(self, api_key, team_id, list_id):
        """
        Initialize the ClickUp service.

        Args:
            api_key (str): ClickUp API key
            team_id (str): ClickUp team ID
            list_id (str): ClickUp list ID for tasks
        """
        self.api_key = api_key
        self.team_id = team_id
        self.list_id = list_id
        self.headers = {"Authorization": api_key}

    def get_users(self):
        """
        Fetch users from ClickUp.

        Returns:
            dict: ClickUp user data
        """
        url = "https://api.clickup.com/api/v2/team"

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.exception(f"Error retrieving ClickUp users: {e}")
            return {"teams": []}

    def correlate_emails_to_ids(self, emails, teams_data):
        """
        Map email addresses to ClickUp user IDs.

        Args:
            emails (list): List of email addresses
            teams_data (dict): ClickUp teams data

        Returns:
            dict: Mapping of emails to ClickUp user IDs
        """
        email_to_id_map = {}

        # Build email to ID mapping from teams data
        for team in teams_data.get("teams", []):
            for member in team.get("members", []):
                user_email = member.get("user", {}).get("email", "")
                user_id = member.get("user", {}).get("id", "")
                email_to_id_map[user_email] = user_id

        # Find user IDs for the given emails
        result = {email: email_to_id_map.get(email, None) for email in emails}
        return result

    def create_task(self, event, assignee_ids):
        """
        Create a task in ClickUp from a calendar event.

        Args:
            event (dict): Processed calendar event
            assignee_ids (list): List of ClickUp user IDs to assign

        Returns:
            bool: Success status
        """
        url = f"https://api.clickup.com/api/v2/list/{self.list_id}/task"

        # Format attendees for description
        amc_attendees = []
        guest_attendees = []

        for attendee in event["attendees"]:
            if any(domain in attendee["email"] for domain in HOST_DOMAINS):
                amc_attendees.append(attendee["email"].split("@")[0].capitalize())
            else:
                guest_attendees.append(attendee["email"])

        attendees_str = ", ".join(sorted(amc_attendees) + sorted(guest_attendees))

        # Create rich description with additional information
        description = f"{event['summary']}\n\n"

        # Add meeting description/agenda if available, cleaned from HTML
        if event["description"]:
            cleaned_description = clean_html(event["description"])
            description += f"Agenda:\n{cleaned_description}\n\n"

        # Add location and meeting link information
        if event["location"]:
            description += f"Location: {event['location']}\n"

        if event["meeting_link"]:
            description += f"Meeting Link: {event['meeting_link']}\n"

        # Add attendees list
        description += f"Attendees: {attendees_str}\n"

        # Add recurrence information if available
        if event["is_recurring"]:
            if event["recurrence"]:
                # Format recurrence rules for better readability
                recurrence_rules = [rule.replace("RRULE:", "") for rule in event["recurrence"]]
                if recurrence_rules:
                    description += f"Recurrence: {', '.join(recurrence_rules)}\n"
            elif event["recurringEventId"]:
                description += f"Part of a recurring series (ID: {event['recurringEventId']})\n"
            else:
                description += "Part of a recurring series\n"

        # Determine meeting type based on if all attendees are internal
        internal_domains = HOST_DOMAINS
        all_attendees_internal = True

        for attendee in event["attendees"]:
            attendee_email = attendee.get("email", "")
            if not any(domain in attendee_email for domain in internal_domains):
                all_attendees_internal = False
                break

        meeting_type = "internal-meeting" if all_attendees_internal else "client-meeting"

        # Map meeting status to priority
        status_priority_map = {
            "confirmed": 3,  # High priority
            "tentative": 2,  # Normal priority
            "cancelled": 1,  # Low priority
        }
        meeting_priority = status_priority_map.get(event["status"], 3)

        # Build tags list
        tags = ["meeting"]

        # Add recurring tag if applicable
        if event["is_recurring"]:
            tags.append("recurring-meeting")

        # Add meeting type tag
        tags.append(meeting_type)

        # Prepare request
        query = {"custom_task_ids": "true", "team_id": self.team_id}

        payload = {
            "name": event["summary"],
            "description": description,
            "time_estimate": int(event["duration"].total_seconds() * 1000),
            "start_date": int(calendar.timegm(event["start"].timetuple()) * 1000),
            "due_date": int(calendar.timegm(event["start"].timetuple()) * 1000),
            "assignees": assignee_ids,
            "priority": meeting_priority,
            "tags": tags,
        }

        headers = {"Content-Type": "application/json", "Authorization": self.api_key}

        logger.debug(f"Creating task: {event['summary']} with attendees: {attendees_str}")
        logger.debug(f"Is recurring: {event['is_recurring']}, Tags: {tags}")

        # Log details about why this is or isn't detected as recurring
        recurring_reasons = []
        if "recurrence" in event:
            recurring_reasons.append("Has 'recurrence' field")
        if event.get("recurringEventId", ""):
            recurring_reasons.append(f"Has 'recurringEventId': {event['recurringEventId']}")
        if event.get("description", "") and "recurring series" in event.get("description", "").lower():
            recurring_reasons.append("Description contains 'recurring series'")

        if event["is_recurring"]:
            logger.debug(f"Recurring meeting reasons: {', '.join(recurring_reasons)}")
        elif recurring_reasons:
            logger.warning(f"Meeting has recurring indicators but wasn't classified as recurring: {recurring_reasons}")

        try:
            response = requests.post(url, json=payload, headers=headers, params=query)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.exception(f"Error creating ClickUp task: {e}")
            return False


class CalendarSyncApp:
    """Main application for syncing Calendar events to ClickUp."""

    def __init__(self):
        """Initialize the application."""
        self.calendar_service = GoogleCalendarService(SERVICE_ACCOUNT_FILE, GOOGLE_CALENDAR_SCOPES)
        self.event_processor = EventProcessor()
        self.clickup_service = ClickUpService(CLICKUP_API_KEY, CLICKUP_TEAM_ID, CLICKUP_LIST_ID)

    def run(self):
        """Execute the sync process."""
        logger.info(f"Starting Calendar to ClickUp sync (v{__version__})...")

        # 1. Fetch calendar events
        logger.info("Fetching calendar events...")
        events = self.calendar_service.get_all_calendar_events(HOST_EMAILS, CALENDAR_SYNC_DAYS)

        # 2. Process events
        logger.info("Processing events...")
        processed_events = self.event_processor.process_events(events)

        # 3. Get ClickUp users
        logger.info("Fetching ClickUp users...")
        teams_data = self.clickup_service.get_users()
        user_id_map = self.clickup_service.correlate_emails_to_ids(HOST_EMAILS, teams_data)

        # 4. Create ClickUp tasks
        logger.info("Creating ClickUp tasks...")
        success_count = 0
        recurring_count = 0
        recurring_types = {"recurrence_field": 0, "recurringEventId_field": 0, "description_text": 0}

        for event_id, event in processed_events.items():
            # Get assignee IDs
            assignee_ids = []
            for attendee in event["attendees"]:
                if attendee["email"] in user_id_map and user_id_map[attendee["email"]]:
                    assignee_ids.append(user_id_map[attendee["email"]])

            # Count recurring events and track detection method
            if event["is_recurring"]:
                recurring_count += 1
                if "recurrence" in event:
                    recurring_types["recurrence_field"] += 1
                if event.get("recurringEventId", ""):
                    recurring_types["recurringEventId_field"] += 1
                if event.get("description", "") and "recurring series" in event.get("description", "").lower():
                    recurring_types["description_text"] += 1

            # Create task
            if self.clickup_service.create_task(event, assignee_ids):
                success_count += 1

        logger.info(f"Sync completed. Created {success_count} of {len(processed_events)} tasks in ClickUp.")
        logger.info(f"Recurring meetings detected: {recurring_count}")
        logger.info(f"Recurring detection breakdown:")
        logger.info(f"  - Via recurrence field: {recurring_types['recurrence_field']}")
        logger.info(f"  - Via recurringEventId field: {recurring_types['recurringEventId_field']}")
        logger.info(f"  - Via description text: {recurring_types['description_text']}")


def main():
    """Main entry point for the application."""
    try:
        app = CalendarSyncApp()
        app.run()
    except Exception as e:
        logger.critical(f"Application failed: {e}", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
