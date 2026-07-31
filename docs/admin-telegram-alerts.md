# Telegram Admin Alerts

The backend can notify one private administrator chat without exposing Telegram credentials to mobile clients.

## Server configuration

Add these values only to `/root/backend/.env` on the server:

```dotenv
NOYTRIX_ADMIN_TELEGRAM_ENABLED=1
NOYTRIX_ADMIN_TELEGRAM_TOKEN=replace_with_bot_token
NOYTRIX_ADMIN_TELEGRAM_CHAT_ID=replace_with_private_numeric_chat_id
NOYTRIX_ADMIN_TELEGRAM_TIMEZONE=Europe/Kyiv
NOYTRIX_ADMIN_TELEGRAM_DAILY_HOUR=23
NOYTRIX_ADMIN_TELEGRAM_DAILY_MINUTE=55
```

The bot token and chat ID must never be committed, added to the mobile app, or pasted into public issue trackers.

## Delivery rules

- Immediately: first registration by email or Google, subscription updates, payment problems, user feedback, and server 5xx errors.
- Daily at 23:55 Kyiv time: one scan summary for that calendar day.
- The summary reads only server-recorded `/scan` events, so mobile retries and front-end analytics cannot inflate it.
- Every alert is written to `backend/data/admin_telegram.sqlite3` before delivery. Repeated webhook events and repeated errors are deduplicated.

## Find the private chat ID

1. Open the administrator bot in Telegram and send it `/start`.
2. In a private terminal, call the Bot API `getUpdates` endpoint for that bot.
3. Copy only the numeric value at `message.chat.id` into `NOYTRIX_ADMIN_TELEGRAM_CHAT_ID`.
4. Restart `noytrix-backend.service` and create a test registration to confirm delivery.

Do not share the bot token with anyone. Rotate it in BotFather after any accidental exposure.
