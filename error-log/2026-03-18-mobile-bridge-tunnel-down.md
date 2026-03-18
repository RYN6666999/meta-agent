# mobile-bridge-tunnel-down incident log

## 2026-03-18 18:10:49
- root_cause: cloudflared tunnel process not running
- solution: restart cloudflared via watchdog
- context: pattern=cloudflared tunnel run --token mode=named
