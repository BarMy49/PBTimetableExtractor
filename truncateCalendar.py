import os
import pickle
import time
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
REQUEST_DELAY = 0.5
MAX_RETRIES = 5


def execute_with_backoff(func):
    delay = 1
    for attempt in range(MAX_RETRIES):
        try:
            return func()
        except HttpError as e:
            if e.resp.status not in (403, 429, 500, 502, 503) or attempt == MAX_RETRIES - 1:
                raise
            print(f"\rBłąd {e.resp.status}, ponawiam za {delay}s...", end="", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 30)


def authenticate():
    print("Uwierzytelnianie...")
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Odświeżanie tokenu...")
            creds.refresh(Request())
        else:
            print("Zaloguj się w przeglądarce...")
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds


def delete_all_events(calendar_id):
    creds = authenticate()
    service = build('calendar', 'v3', credentials=creds)

    print("Pobieranie wydarzeń planu (pbte=1)...")
    managed = []
    page_token = None
    while True:
        events = execute_with_backoff(
            lambda: service.events().list(
                calendarId=calendar_id,
                pageToken=page_token,
                privateExtendedProperty="pbte=1"
            ).execute()
        )
        for event in events.get('items', []):
            managed.append((event['id'], event.get('summary', '(bez tytułu)')))
        page_token = events.get('nextPageToken')
        if not page_token:
            break

    total = len(managed)
    if total == 0:
        print("Nie znaleziono wydarzeń do usunięcia.")
        return

    for i, (event_id, summary) in enumerate(managed, 1):
        execute_with_backoff(
            lambda: service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
        )
        print(f"\rUsuwanie ({i}/{total}): {summary}...", end="", flush=True)
        time.sleep(REQUEST_DELAY)

    print(f"\nUsunięto łącznie: {total}")


if __name__ == "__main__":
    calendar_id = "fb71fba1febe4271f784c839e1c5b73d01e417d257c9036ae04c54d0d6565187@group.calendar.google.com"
    delete_all_events(calendar_id)
