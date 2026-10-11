# ClaimScout privacy

ClaimScout has no servers and no accounts. It runs on your PC and your phone. This page lists every place your
data goes.

## On your PC

`~/.local/share/claimscout` holds:

- your profile: the companies you've used, the states you've lived in and your questionnaire answers
- the settlement listings, match scores and your claims (claim numbers, status, notes)
- **facts** taken from emails that prove something (sender, date, subject, amount, order number, a one-line
  summary and a link to reopen the email) — not the emails themselves
- payout emails the watcher found (sender, subject, kind, amount, expiry, link)
- the server's TLS key and the phone's pairing token

Nothing in it is sent anywhere, except as listed under "AI" below.

## On your phone

- Gmail app passwords and Outlook sign-in tokens, sealed with an Android Keystore key. They are used only to
  talk to Google's IMAP server and Microsoft Graph, and never leave the phone.
- The pairing (PC address, token, certificate fingerprint) and a few settings.
- Android backup is off for the app, so none of this is copied to Google Drive or a new phone.

Permissions: **Internet**, **Notifications** (new matches, deadlines, money waiting) and **Camera**, used only while
you scan the pairing QR code; nothing is saved or sent. Android also lists the background-work permissions
(wake lock, run at startup) that the scheduled email checks need.

## Email

Email is searched **from the phone**, read-only, with the search plan your PC made (senders, keywords, dates).
Only matching messages, cut to 4,000 characters each, are sent to your PC over HTTPS pinned to your PC's
certificate. The payout watcher does the same every 4 hours, including your Spam/Junk folder, looking only for
settlement administrators and payment services.

## Network requests your PC makes

- the public settlement lists (Top Class Actions, ClassAction.org, OpenClassActions) and any community lists you
  add, every 6 hours
- logos: Super Tiny Icons and Simple Icons (via the jsDelivr CDN), Wikidata/Wikimedia Commons and the company's own
  website. These requests contain a company name, never anything about you.

## AI

AI is optional and off by default.

- **Model on your PC** (llama.cpp, Ollama, LM Studio): nothing leaves the PC.
- **OpenRouter**: settlement text, your profile (companies and states) and the email excerpts being checked go to
  OpenRouter and the model's host. Free models may log prompts. Choose this only if you're comfortable with that.

## Removing everything

Run `~/claimscout/install.sh --uninstall` (or stop the service: `systemctl --user disable --now claimscout`),
delete `~/.local/share/claimscout`, uninstall the app, and revoke the Gmail app password at
https://myaccount.google.com/apppasswords.

Questions: open an issue at https://github.com/TheWiderLensInitiative/claimscout/issues
