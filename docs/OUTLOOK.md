# Connecting Outlook (one-time, free, about 3 minutes)

Microsoft needs an "app registration" before any app can read mail through Microsoft Graph. It's free and no
secret is involved. You can make one yourself, or the person who builds the APK can make one for everyone and
put its ID in `android/gradle.properties` (`claimscout.microsoftClientId=`).

1. Open https://entra.microsoft.com and sign in with any Microsoft account (an Outlook.com account works).
2. Go to **App registrations → New registration**.
   * Name: `ClaimScout`
   * Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**
   * Redirect URI: leave empty
   * Click **Register**.
3. Under **Authentication → Advanced settings**, set **Allow public client flows** to **Yes**, then **Save**.
   This turns on the code sign-in the app uses.
4. Under **API permissions**, check that `Microsoft Graph → User.Read` is listed. The app also asks for
   `Mail.Read` and `offline_access` when you sign in; you don't have to add them here.
5. Copy the **Application (client) ID** from **Overview** and paste it into ClaimScout on the phone
   (**Settings → Microsoft app client ID**).

Then tap **Add Outlook**. The app shows a short code; enter it at microsoft.com/link and approve. ClaimScout can
only read mail. Remove it anytime at https://account.live.com/consent/Manage.

Work or school accounts may need an admin to approve the app.
