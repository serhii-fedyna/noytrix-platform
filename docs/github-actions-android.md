# Android Production CI/CD

The workflow at `.github/workflows/android-internal-release.yml` runs on every
push to `master` and can also be started manually from GitHub Actions.

It performs the following steps:

1. Installs the mobile dependencies with `npm ci`.
2. Validates the Expo configuration.
3. Bundles the Android JavaScript as a CI test.
4. Restores the protected Google services file from a GitHub secret.
5. Uses EAS-managed versioning to increment `versionCode` and build the signed
   Android App Bundle. The version is kept in EAS so repeated CI runs cannot
   reuse the same Google Play version number.
6. Uploads the completed release to the Google Play Production track.

Google Play may still hold a release for its review. After Google approves it,
the update becomes available to users according to Google Play rollout and
device auto-update rules.

## One-time manual setup

Create these GitHub Actions repository secrets under
`Settings -> Secrets and variables -> Actions`:

| Secret | Value |
|---|---|
| `EXPO_TOKEN` | An Expo access token with access to the `hitkrit/noytrix-s54` project. |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | The complete JSON key for the Google service account that has release permission for `com.noytrix.app`. |
| `GOOGLE_SERVICES_JSON_B64` | Base64 contents of the app's `google-services.json`. |

Do not commit any of these values or paste them into issues, chat, or logs.

## Google Play API access

If the existing service account is not already linked:

1. In Google Cloud, enable **Google Play Android Developer API**.
2. Create or use the Google Play service account and download its JSON key.
3. In Play Console, link the Cloud project under **API access**.
4. Invite the service account email under **Users and permissions**.
5. Grant permission to manage production releases and release apps to testing
   tracks.

The package name must remain `com.noytrix.app`.

## Creating the protected values

Create `EXPO_TOKEN` in the Expo account settings. The token must be allowed to
build the Noytrix EAS project.

For `GOOGLE_SERVICES_JSON_B64`, run PowerShell locally and copy the output
directly into the GitHub secret field:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\google-services.json"))
```

For `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`, paste the complete downloaded JSON into
the GitHub secret field. Never put that JSON in the repository.

## First run

After all three secrets are present, push a normal commit to `master` or start
**Android Production Release** from the Actions tab. A failed build does not
publish anything. A successful upload submits the release to Google Play
Production and may trigger Google Play review before users receive it.
