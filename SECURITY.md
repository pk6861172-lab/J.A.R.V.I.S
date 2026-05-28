Production Hardening Checklist

JARVIS is safe to share as source code only when every user creates their own
private configuration. Do not commit real API keys, Telegram tokens, email app
passwords, OAuth tokens, face images, generated sessions, browser profiles,
local certificates, or runtime logs.

Use `jarvis_config.template.json` and `.env.example` as examples only. Copy them
to private local files (`jarvis_config.json` and `.env`) before adding real
credentials.

Safe-by-default controls:
- Weak web tokens such as `jarvis`, `1234`, `admin`, and short tokens are rejected.
- Web auth does not accept hardcoded passcodes or loopback-only face bypasses.
- Backend task, approval, agent, and WebSocket endpoints require a strong token.
- Telegram control should be owner-only through `telegram_allowed_user_id`.
- Non-owner AI auto-replies are disabled by default.
- Self-improvement requests are guarded. JARVIS blocks requests to bypass auth,
  reveal secrets, run covert surveillance, or keep the camera always on.

If you fork or publish this project, rotate any secret that was ever committed,
uploaded, pasted into an assistant, or shown publicly.

1. Secrets & keys
- Generate a strong ADMIN_API_KEY and set in .env
- Ensure token_storage uses cryptography.Fernet (install cryptography)

2. TLS
- Obtain Let's Encrypt certs and mount into backend/certs
- Use deploy/nginx.conf and docker-compose.prod.yml for production

3. TURN
- Provision a public VM for coturn using terraform or cloud console
- Set TURN_EXTERNAL_IP in environment and open required ports

4. Agent security
- Use ADMIN API key for all admin endpoints
- Limit autonomous tasks by allowlist and require manual approval for destructive actions
- Set rate limits (RATE_LIMIT_REQ, RATE_LIMIT_WINDOW env vars)

5. Observability
- Centralize audit logs (rotate daily)
- Add Prometheus metrics and alerts for agent runner

6. CI/CD
- Add GitHub Actions to build images and run tests before deploy

7. Backup
- Regular DB backups and encrypted token backups
