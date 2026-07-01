#!/usr/bin/env bash
curl -s -X POST "http://127.0.0.1:8000/api/calendar/events/refresh" >/dev/null 2>&1
