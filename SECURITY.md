# Security

ClaimScout reads your email (read-only, from the phone) and keeps your claim history on your PC, so security
matters. What goes where is described in [docs/PRIVACY.md](docs/PRIVACY.md).

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Use GitHub's private vulnerability reporting
(Security tab → "Report a vulnerability") or email claimscout@thewiderlens.info, with steps to reproduce. We'll reply as soon as we can.

## How it's protected

- The phone talks to the PC over HTTPS pinned to the PC's own certificate (its SHA-256 fingerprint is in the
  pairing link), with a random bearer token. `claimscout reset-token` unpairs every phone.
- The dashboard listens on 127.0.0.1 only; the pairing code is shown only to the PC itself.
- Email passwords and Outlook tokens never leave the phone. They are sealed with an Android Keystore key and
  excluded from backups.
- Links from listings and community lists are accepted only if they are `http(s)`.

## Good practice for users

- Keep port 8787 on your home network or Tailscale. Don't forward it on your router to the internet.
- Use a Gmail **app password** (revocable at any time), never your normal password.
- Keep `~/.local/share/claimscout` private and backed up; it holds your profile, claims and the server's key.
