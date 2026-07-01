from datetime import datetime, timezone

def fetch():
    return [
        dict(
            title="ECB Rate Decision — European Central Bank",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 10, 12, 45, tzinfo=timezone.utc),
            source_url="https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
            summary="ECB interest rate decision (EUR impact)"
        ),
        dict(
            title="ECB Press Conference — European Central Bank",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 10, 13, 30, tzinfo=timezone.utc),
            source_url="https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
            summary="ECB press conference (Lagarde)"
        ),
    ]
