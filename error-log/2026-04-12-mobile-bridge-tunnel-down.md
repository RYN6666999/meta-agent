# mobile-bridge-tunnel-down incident log

## 2026-04-12 00:24:38
- root_cause: cloudflared tunnel process not running
- solution: restart cloudflared via watchdog
- context: pattern=cloudflared tunnel run --token mode=named
