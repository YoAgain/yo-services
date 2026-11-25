# Yo Services

Services you can [Yo](https://github.com/YoAgain/yo). PING and YoGPT run.

| Yo | Does |
|---|---|
| [PING](yo/ping) | Sends back what you send |
| [YoGPT](yo/yogpt) | Thinks for a moment, then sends a picture |

## How it works

To the hub, a service is a user like any other. The server starts its script for each Yo; the script never sees who you
are.

```text
                Your phone
                    │
┌───────────────────┴────────────────────┐
│ Hub                                    │
│ Delivers Yos. Cannot read them.        │
└───────────────────┬────────────────────┘
┌───────────────────┴────────────────────┐
│ Executor                               │
│ Has the account. Checks with ping.toml │
└───────────────────┬────────────────────┘
┌───────────────────┴────────────────────┐
│ ping.py                                │
│ Decides the answer. No keys, no net.   │
└────────────────────────────────────────┘
```

## Build one

Copy [template](template): `template.toml` says what it may do, `template.py` does it, `assets/` holds its pictures.
`python3 test.py` checks it. All four fields are required.

| | |
|---|---|
| `names` | Its Yo names, one or more; `event["name"]` says which was Yoed |
| `about` | What it does |
| `triggers` | `"yo"`: answers a Yo, remembers nobody |
| | `"cron"`: one reminder per Yo, remembers who until then |
| | `"webhook"`: planned |
| `allowed_urls` | Web addresses it may call, planned |

License and everything else: [Yo](https://github.com/YoAgain/yo#readme).
