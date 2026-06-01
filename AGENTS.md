# Discord Quest Auto-Completer — Agent Instructions

## Task Tracking
- Dùng `.todo.md` để track task list, không dùng `todowrite` tool.
- Format checklist: `- [ ]` pending, `- [/]` in progress, `- [x]` completed, `- [-]` cancelled.
- Ghi đè `.todo.md` sau mỗi step khi state thay đổi.

## Code Style
- Functional > class (nếu đơn giản)
- async/await > sync
- camelCase cho biến/hàm, PascalCase cho type
- Import order: builtin → third-party → local
- Type hints bắt buộc mọi function
- Không thêm comments trừ khi được yêu cầu

## Commands
- Lint: `ruff check src/`
- Test: `pytest tests/ -v`
- Run: `python -m discord_quest`
