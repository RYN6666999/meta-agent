# mobile-bridge-tunnel-down incident log

## 2026-04-17 00:07:38
- root_cause: cloudflared tunnel process not running
- solution: restart cloudflared via watchdog
- context: pattern=cloudflared tunnel run --token mode=named
