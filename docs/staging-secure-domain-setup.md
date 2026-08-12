# Secure Noytrix Staging

The preview at `http://157.173.118.5:8100` is intentionally limited to public scans.
It must not accept credentials or expose entitlement data because it is not encrypted.

## Required DNS change

Create this DNS record in the provider that manages `noytrix.com`:

| Type | Name | Value |
| --- | --- | --- |
| A | `staging` | `157.173.118.5` |

This creates `staging.noytrix.com`. Allow DNS propagation, then notify the engineering owner.

## What will be enabled after DNS is live

1. HTTPS certificate and redirect from HTTP to HTTPS.
2. Login, registration and password reset through the existing Noytrix backend.
3. Google sign-in through the existing Google OAuth web client.
4. Server-backed `/iap/account-status`, so the same Noytrix account sees the same verified PRO entitlement on web and mobile.

## Google OAuth configuration

In the existing **Noytrix Web** OAuth client, add this authorized JavaScript origin:

`https://staging.noytrix.com`

Do not add credentials to this repository or to the browser. The browser receives only the public Google OAuth client ID; all account and entitlement decisions remain on the Noytrix server.
