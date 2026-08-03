# AI Job Hunter v3.1 — fixed

This version fixes the previous Gemini error:

`Cannot send a request, as the client has been closed.`

## Main changes

- Gemini 2.5 Flash is called through the REST API instead of creating a new SDK client for every job.
- Retries Gemini 429 and 5xx errors.
- Ranks jobs before using the AI, so the free API is spent on the strongest candidates.
- Evaluates up to 100 high-quality candidates per workflow.
- Uses conservative request pacing.
- No fake `MATCH: 80%` result when Gemini fails.
- No unrelated software-development fallback.
- Keeps Junior, Entry Level, Graduate, Internship, Trainee, L1/Tier 1 and Remote.
- Senior/Sr is accepted when the actual experience requirement is realistically <=2 years.
- Sends up to 12 best matches to Telegram.
- Tracks previously evaluated URLs to reduce duplicates.

## Secrets required

GitHub repository → Settings → Secrets and variables → Actions:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Important

This project searches public job data and public web pages. It does not bypass
CAPTCHA, login walls, anti-bot controls, or private APIs.

It discovers and ranks jobs and gives an application link. It does NOT submit
applications automatically yet.
