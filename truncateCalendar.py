import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def delete_all_events(calendar_id):
    creds = authenticate()
    service = build('calendar', 'v3', credentials=creds)

    page_token = None
    total_deleted = 0

    while True:
        events = service.events().list(
            calendarId=calendar_id,
            pageToken=page_token
        ).execute()

        for event in events.get('items', []):
            service.events().delete(
                calendarId=calendar_id,
                eventId=event['id']
            ).execute()
            total_deleted += 1
            print(f"Deleted: {event.get('summary')}")

        page_token = events.get('nextPageToken')
        if not page_token:
            break

    print(f"\nTotal deleted: {total_deleted}")

if __name__ == "__main__":
    calendar_id = "fb71fba1febe4271f784c839e1c5b73d01e417d257c9036ae04c54d0d6565187@group.calendar.google.com"
    delete_all_events(calendar_id)