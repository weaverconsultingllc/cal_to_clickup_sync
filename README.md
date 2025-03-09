# Calendar to ClickUp Sync

This application synchronizes Google Calendar events to ClickUp tasks for capacity planning and resource management.

## Overview

The application retrieves upcoming events from Google Calendar for specified users and creates corresponding tasks in ClickUp. This allows managers to see the meeting load of employees for better capacity planning.

## Features

- Retrieves calendar events for the next 14 days (configurable)
- Processes and deduplicates events across multiple users
- Creates tasks in ClickUp with rich metadata:
  - Accurate time estimates based on meeting duration
  - Meeting description/agenda
  - Location information (physical or virtual)
  - Meeting link for virtual meetings
  - Tags for recurring vs. one-time meetings
  - Tags for internal vs. client meetings (based on attendee composition)
  - Priority based on meeting status (confirmed, tentative, cancelled)
  - Full attendee list

## Configuration

All configuration options are available in `config.py`:

- `GOOGLE_CALENDAR_SCOPES`: API scopes for Google Calendar
- `SERVICE_ACCOUNT_FILE`: Path to Google service account credentials
- `CALENDAR_SYNC_DAYS`: Number of days to look ahead for events
- `HOST_EMAILS`: List of email addresses to sync calendars for
- `CLICKUP_API_KEY`: ClickUp API key
- `CLICKUP_TEAM_ID`: ClickUp team ID
- `CLICKUP_LIST_ID`: ClickUp list ID for tasks
- `DEBUG`: Enable debug logging
- `LOG_FILE`: Path to log file

## Additional Features

- **HTML Cleaning** - Automatically converts HTML-formatted meeting descriptions to clean, readable text
- **Meeting Type Detection** - Intelligently identifies internal meetings vs. client meetings based on all attendees
- **Enhanced Recurring Meeting Detection** - Uses multiple methods to identify recurring meetings:
  - Google Calendar API fields (`recurrence` and `recurringEventId`)
  - Meeting description text analysis
  - Provides detailed logs about detection methods
- **Rich Meeting Context** - Includes recurrence information, location details, and conference links

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy the file `config.example.py` to `config.py`
2. Set up Google Calendar API and ClickUp API credentials in `config.py`
3. Run the application: `python calendar_sync.py`

## Usage

```bash
python calendar_sync.py
```

## Requirements

- Python 3.6+
- Google Calendar API access
- ClickUp API access

## Dependencies

- google-api-python-client
- google-auth
- requests
