# mobile-bridge-url-missing incident log

## 2026-03-17 17:27:31
- root_cause: cloudflared did not emit quick tunnel url
- solution: keep watchdog retries and restart tunnel
- context: log=/tmp/meta-agent-cloudflared.log
