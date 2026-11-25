# IFTTT

How Anna connects Yo with IFTTT, and what happens then. Planned: not running yet.

## Connect

```text
Anna                    IFTTT                     Yo
 │   "Connect Yo"         │                        │
 ├───────────────────────►│  opens, with state=777 │
 │                        ├───────────────────────►│  api.justyo.app/ifttt/connect
 │                                                 │  right client_id and redirect_uri? a request, 10 minutes
 │   justyo.co/services/ifttt#…                    │
 │◄────────────────────────────────────────────────┤  a QR code, or "Open in Yo"
 │   opens the app: "Connect IFTTT?" Allow         │
 ├────────────────────────────────────────────────►│  encrypted, to the account IFTTT
 │                                                 │  keeps: this request is Anna's
 │   the page goes back by itself                  │
 ├───────────────────────►│  return_url?code=…&state=777
 │                        │  the code, for a key   │
 │                        ├───────────────────────►│  api.justyo.app/ifttt/token
 │                        │◄───────────────────────┤  Anna's key, for good
```

The code is new, good once and for 5 minutes. The page knows no state: it draws the code of the request and asks
`api.justyo.app/ifttt/allowed` until it is told where to go. For IFTTT:

| | |
|---|---|
| Authorization URL | `https://api.justyo.app/ifttt/connect` |
| Token URL | `https://api.justyo.app/ifttt/token` |
| Client id, redirect URL | [ifttt.toml](ifttt.toml) |
| Client secret, service key | two different ones, the server's |

From now on the server has one row for Anna:

| service | user | in | out |
|---|---|---|---|
| IFTTT | Anna | her key (hashed): IFTTT calls with it | her id, the same after a reconnect: we tell IFTTT whom it is about |

## IFTTT → Anna

It rains, and Anna's Applet says "Yo me".

```text
IFTTT ──► api.justyo.app/ifttt/v1/actions/yo_me      with Anna's key (in)
          server      whose key is it? Anna's
          ifttt.py    [{"send": "yo"}, {"reply": …}]      or with photo_url: a picture
Anna  ◄── Yo from IFTTT
```

## Anna → IFTTT

Anna Yos IFTTT, and her Applet turns on the light. IFTTT takes no Yo from us: it is told there is one, then asks for it.

```text
Anna  ──► Yo to IFTTT
          server      keeps it for 7 days at most, tells the newest 50
          ifttt.py    [{"call": "https://realtime.ifttt.com/v1/notifications", …}]
IFTTT ◄── there is something new for Anna (out)
IFTTT ──► api.justyo.app/ifttt/v1/triggers/you_yo_ifttt      with Anna's key (in)
          server      whose key is it? Anna's: her last Yos
          ifttt.py    [{"reply": …}]
IFTTT ◄── one Yo, 18:00
          light on
```

## Who does what

| | |
|---|---|
| [ifttt.toml](ifttt.toml) | Where the user goes back to, what may be called |
| [ifttt.py](ifttt.py) | IFTTT's questions, our answers. No keys, no net, never learns who Anna is |
| Server ([yo](https://github.com/YoAgain/yo)) | Connects, keeps in and out, checks every secret, sends the Yos |
