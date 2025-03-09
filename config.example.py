"""
Configuration settings for the Calendar to ClickUp sync application.
"""

# Google Calendar API settings
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
SERVICE_ACCOUNT_FILE = "your-google-service-account-creds-file-here.json"

# Calendar sync settings
CALENDAR_SYNC_DAYS = 14  # Number of days to look ahead
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
DATE_FORMAT_NO_TIME = "%Y-%m-%d"

# User accounts to sync
# Email addresses in your Google Suite Gmail you want to pull calender events from
# These are expected to be the same as your ClickUp team members
HOST_EMAILS = ["angela@mycompany.com", "chris@mycompany.com", "brandy@mycompany.com", "christine@mycompany.com"]

# The domains for the internal employees
# If a meeting has attendees with only these domains, it is considered an internal meeting
HOST_DOMAINS = ["mycompany.com"]

# ClickUp API settings
CLICKUP_API_KEY = "put your clickup API key here"
CLICKUP_TEAM_ID = "your clickup team ID"  # the ID of your team
CLICKUP_LIST_ID = "your clickup list id"  # the ID of the list where you want the events to be added

# Logging settings
DEBUG = True
LOG_FILE = "./calendar_sync.log"
