# Telegram API relay (optional workaround)

Use only if outbound `https://api.telegram.org` is unreachable from the Russian Yandex Cloud Functions network.
The existing YDB remains in ru-central1. Outbound Telegram messages and the BotFather token pass through **Cloudflare**, a third-party service outside Russia; enable this only if acceptable for your data flow.

## 1. Deploy relay in your own Cloudflare account

1. Open https://dash.cloudflare.com/ and sign in (Workers Free plan).
2. Open **Workers & Pages → Create application → Create Worker**. Name it `moi-dela-telegram-relay` and deploy.
3. Open **Edit code**. Replace the starter code with `cloudflare/telegram-proxy.js`; **Deploy** again.
4. In the Worker's **Settings → Variables and Secrets**, create a **Secret** (not public variable) named `PROXY_KEY` with a random value of at least 32 characters. Use `openssl rand -hex 32` locally to generate one. Never commit this value.
5. Copy the Worker's HTTPS URL, e.g. `https://moi-dela-telegram-relay.<account>.workers.dev`.

## 2. Update the Yandex Telegram function

Update the existing `moi-dela-telegram` function. Keep the working YDB settings and service account.
Upload a new ZIP built from the repository's **top-level runtime .py files** plus `requirements.txt`; do not use the GitHub auto-download ZIP as it nests files one directory too deep.

Existing variables remain:
`TELEGRAM_BOT_TOKEN`, `YDB_ENDPOINT`, `YDB_DATABASE`, `BOT_TIMEZONE`.

Add:
- `TELEGRAM_API_PROXY_URL` = your personal Worker's HTTPS URL (no trailing slash)
- `TELEGRAM_PROXY_KEY` = exactly the same secret value as Cloudflare's `PROXY_KEY`.

Keep entry point `main.handler`, Python 3.12 and service account `moi-dela-sa`.

Yandex Cloud's existing Telegram **trigger v2** remains unchanged. The relay is for **outbound** Bot API requests only. Do not register another webhook or install a second Telegram trigger.

## 3. Check

Send `/start` to your bot. Expect the menu with three actions.
Then add a test task and verify its text and Excel file. Remember that timed reminders also require the separate `scheduler_main.handler` timer trigger.

If `/start` still fails, check function invocation and reachability of your own Worker URL from Yandex Cloud. Even this relay cannot guarantee network availability.

## Security

- This Worker accepts only POST and four Bot API methods (`sendMessage`, `editMessageText`, `answerCallbackQuery`, `sendDocument`). Other methods are rejected.
- It requires a shared proxy secret and the bot token in HTTPS headers. No token in the public Worker URL or repository.
- Do not add logging of headers or payloads. Keep Worker and Yandex environment variables private.
- The Cloudflare account is a separate service, with its own service availability and privacy/data-transfer implications.
- Cloudflare Workers Free currently limits requests to 100,000/day; availability and prices may change.
