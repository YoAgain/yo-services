# IFTTT

How Anna connects Yo with IFTTT, and what happens then. Planned: not running yet.

## Connect

```text
Anna                    IFTTT                     Yo
 │   "Connect Yo"         │                        │
 ├───────────────────────►│                        │
 │                        │  opens                 │
 │                        ├───────────────────────►│  justyo.co/services/ifttt/connect?state=777
 │                                                 │  shows a QR code, or "Open in Yo"
 │   opens the app: "Connect IFTTT?" Allow         │
 ├────────────────────────────────────────────────►│  encrypted, to the account IFTTT
 │                                                 │  keeps: 777 is Anna
 │   "Continue"           │                        │
 ├───────────────────────►│  return_url?code=777   │
 │                        │  777, for a secret     │
 │                        ├───────────────────────►│  api.justyo.app/ifttt/token
 │                        │◄───────────────────────┤  Anna's secret, for good
```

From now on the server has one row for Anna:

| service | user | in | out |
|---|---|---|---|
| IFTTT | Anna | her secret (hashed): IFTTT calls with it | her id: we tell IFTTT whom it is about |

## IFTTT → Anna

It rains, and Anna's Applet says "Yo me".

```text
IFTTT ──► api.justyo.app/ifttt/v1/actions/yo_me      with Anna's secret (in)
          server      whose secret is it? Anna's
          ifttt.py    [{"send": "yo"}, {"reply": …}]      or with photo_url: a picture
Anna  ◄── Yo from IFTTT
```

## Anna → IFTTT

Anna Yos IFTTT, and her Applet turns on the light. IFTTT takes no Yo from us: it is told there is one, then asks for it.

```text
Anna  ──► Yo to IFTTT
          server      keeps it for 7 days
          ifttt.py    [{"call": "https://realtime.ifttt.com/v1/notifications", …}]
IFTTT ◄── there is something new for Anna (out)
IFTTT ──► api.justyo.app/ifttt/v1/triggers/you_yo_ifttt      with Anna's secret (in)
          server      whose secret is it? Anna's: her last Yos
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
