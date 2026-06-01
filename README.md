# Discord Quest Auto-Completer

Tự động quét, nhận và hoàn thành Quest trên Discord.

## Tính năng

| Tính năng | Mô tả |
|---|---|
| **Auto Scan** | Quét quest mới theo chu kỳ (`poll_interval`) |
| **Auto Enroll** | Tự động đăng ký quest chưa nhận |
| **Auto Complete** | Gửi heartbeat/video-progress để hoàn thành quest |
| **Rate Limit Handling** | Retry với exponential backoff khi bị 429 |
| **Build Number Fetch** | Lấy `client_build_number` động từ Discord web app |
| **Gateway** | WebSocket real-time nhận quest update |
| **Persist** | Lưu quest đã hoàn thành vào SQLite (tránh trùng lặp) |

## Cài đặt

```bash
pip install -e .
```

Yêu cầu Python >= 3.12.

## Sử dụng

```bash
# Từ file .token
discord-quest

# Custom interval + proxy + debug
discord-quest --poll-interval 120 --proxy http://127.0.0.1:8080 --debug

# Hoặc qua module
python -m discord_quest
```

Token được đọc theo thứ tự: `.token` file → nhập thủ công (ẩn).

## Cấu hình

Biến môi trường prefix `DQ_` hoặc file `.env`:

| Biến | Mặc định | Mô tả |
|---|---|---|
| `DQ_API_BASE` | `https://discord.com/api/v9` | Discord API base URL |
| `DQ_POLL_INTERVAL` | `60` | Chu kỳ quét (giây) |
| `DQ_HEARTBEAT_INTERVAL` | `20` | Chu kỳ heartbeat (giây) |
| `DQ_AUTO_ACCEPT` | `true` | Tự động enroll quest |
| `DQ_LOG_PROGRESS` | `true` | Log tiến độ |
| `DQ_DEBUG` | `true` | Debug log |
| `DQ_REQUEST_TIMEOUT` | `30` | HTTP timeout (giây) |
| `DQ_PROXY` | — | Proxy URL |
| `DQ_BUILD_FALLBACK` | `504649` | Build number dự phòng |

## Cấu trúc mã nguồn

```
src/discord_quest/
├── __init__.py          # Public API exports
├── __main__.py          # CLI entry (argparse)
├── _api.py              # DiscordAPI: httpx AsyncClient + build number
├── _completer.py        # QuestAutocompleter: core logic + heartbeat helpers
├── _config.py           # Settings: Pydantic Settings (env prefix DQ_)
├── _gateway.py          # DiscordGateway: WebSocket + reconnection
├── _log.py              # structlog setup (ConsoleRenderer/JSONRenderer)
├── _models.py           # Dataclasses: Quest, UserStatus, QuestProgress
└── _persist.py          # StateStore: SQLite (WAL mode)
```

### Kiến trúc

```
__main__.py  (CLI argparse)
     │
     ▼
_completer.py  (QuestAutocompleter)
     │
     ├── _api.py        — HTTP requests + build number
     ├── _gateway.py    — WebSocket real-time
     ├── _models.py     — Data structures
     ├── _persist.py    — SQLite persistence
     └── _config.py     — Settings + _log.py setup
```

### Luồng hoạt động

```
Start
  ├─ Đọc token
  ├─ Fetch build number
  ├─ Validate token
  ├─ Connect gateway (WebSocket)
  └─ Loop (mỗi POLL_INTERVAL):
       ├─ GET /users/@me/quests
       ├─ Enroll quest chưa nhận
       └─ Process từng quest:
            ├─ WATCH_VIDEO*  → POST video-progress
            └─ PLAY/STREAM*  → POST heartbeat + complete
```

### Loại quest hỗ trợ

| Task | Endpoint | Cơ chế |
|---|---|---|
| `WATCH_VIDEO` | `/video-progress` | POST timestamp tăng dần |
| `WATCH_VIDEO_ON_MOBILE` | `/video-progress` | Giống WATCH_VIDEO |
| `PLAY_ON_DESKTOP` | `/heartbeat` | Heartbeat 20s + stream_key ngẫu nhiên |
| `STREAM_ON_DESKTOP` | `/heartbeat` | Giống PLAY_ON_DESKTOP |
| `PLAY_ACTIVITY` | `/heartbeat` | Heartbeat 20s + stream_key cố định |
