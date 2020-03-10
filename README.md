# Telegram Public Mask Finder Bot

## Introduction

Provides information of S. Korea's Public Mask sale status.

## Built with...

- Python (3.8)
- asyncio
- [aiogram](https://github.com/aiogram/aiogram)
- [aiohttp](https://github.com/aio-libs/aiohttp)
- [Trafaret](https://github.com/Deepwalker/trafaret)
- [Official API](https://app.swaggerhub.com/apis-docs/Promptech/public-mask-info/20200307-oas3)

## Self-hosting instructions

### Prequisites

- Python >= 3.8
- Telegram Bot Token

### Instruction

1. Install requirements with `pip install -r requirements.txt`
2. Create dotenv(`.env`) file containing telegram bot's token. The file should be formed like:

```sh
BOT_TOKEN=SOME_TELEGRAM_BOT_TOKEN
```

3. Start bot with `python bot.py`.
