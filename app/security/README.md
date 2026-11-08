# app/security (Phase 17)

| Module | Does |
| --- | --- |
| `passwords.py` | PBKDF2-SHA256 password hashes (600,000 rounds, random salt) |
| `users.py` | Accounts in `USERS_FILE` (employee / manager / admin), `Principal` = who is calling |
| `tokens.py` | Signed login tokens (JWT, HS256) |
| `access.py` | Who may see whose data: self / team (manager chain) / everyone; tenants |
| `rate_limit.py` | Sliding-window limits → 429 with Retry-After |
| `audit.py` | `logs/audit.jsonl`: who did what, never request bodies |
| `prompt_injection.py` | Detects and removes instructions aimed at the AI assistant |
| `uploads.py` | Upload content must match its extension (no renamed programs) |

The API wires them in `app/api/dependencies.py` and `app/main.py`. Guide: `docs/SECURITY_GUIDE.md`.
