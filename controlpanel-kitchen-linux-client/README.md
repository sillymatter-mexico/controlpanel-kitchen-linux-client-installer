# controlpanel-kitchen-linux-client

Async Python client for the [ControlPanel Kitchen](https://api.controlpanel.kitchen) API.

## Requirements

- Python 3.12+
- [Poetry](https://python-poetry.org/)

## Setup

```bash
make install
```

## Usage

```python
import asyncio
from controlpanel_kitchen_api import ControlPanelKitchenClient

async def main():
    # Login to obtain a token
    async with ControlPanelKitchenClient() as client:
        login = await client.auth.login("user@example.com", "password")

    # Use the token for subsequent requests
    async with ControlPanelKitchenClient(token=login.token) as client:
        me = await client.auth.me()
        collectors = await client.collectors.list()
        print(me, collectors)

asyncio.run(main())
```

Environment variables (prefix `CPK_`):

| Variable | Default |
|---|---|
| `CPK_TOKEN` | *(none)* |
| `CPK_BASE_URL` | `https://api.controlpanel.kitchen` |
| `CPK_TIMEOUT` | `30.0` |
| `CPK_ORGANIZATION_HOST` | *(none)* |

## Development

```bash
make test          # run tests
make lint          # ruff check
make format        # ruff format

# Regenerate Pydantic models from the live OpenAPI schema:
make generate-schemas
```
