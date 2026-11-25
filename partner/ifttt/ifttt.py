"""IFTTT's own API (https://ifttt.com/docs/api_reference): "You Yo IFTTT" runs an Applet, "Yo me" Yos its user.

IFTTT takes no Yo from us: it is told there is one, then asks for it.
"""
import json
import sys
from datetime import datetime, timezone

TRIGGER, ACTION = "you_yo_ifttt", "yo_me"
KINDS = {"picture": "photo"}


def yos(event):
    """The user's Yos to IFTTT, newest first."""
    sent = event["yos"]
    if event["out"] == "test":                # IFTTT's own tests want three
        sent = [{"id": f"test{n}", "kind": "yo", "at": 1_700_000_000 + n} for n in (3, 2, 1)]
    limit = event["body"].get("limit")
    if type(limit) is not int:
        limit = 50
    return [{
        "received_at": datetime.fromtimestamp(yo["at"], timezone.utc).isoformat(),
        "kind": KINDS.get(yo["kind"], yo["kind"]),
        "meta": {"id": yo["id"], "timestamp": yo["at"]},
    } for yo in sent[:max(limit, 0)]]


def refuse(code, why, **more):
    return [{"reply": {"errors": [{"message": why, **more}]}, "status": code}]


def called(event):
    """IFTTT calls us."""
    call = event["method"] + " " + event["path"].removeprefix("v1/")
    if call in ("GET status", "POST test/setup"):               # with IFTTT's own key, not a user's
        if not event["keyed"]:
            return refuse(401, "No service key")
        if call == "GET status":
            return [{"reply": {}}]
        if not event["test"]:
            return refuse(503, "No test account")
        samples = {"triggers": {TRIGGER: {}}, "actions": {ACTION: {"photo_url": ""}}}
        return [{"reply": {"data": {"accessToken": event["test"], "samples": samples}}}]
    if call.startswith(f"DELETE triggers/{TRIGGER}/trigger_identity/"):
        return [{"reply": {}}]
    if call not in ("GET user/info", f"POST triggers/{TRIGGER}", f"POST actions/{ACTION}"):
        return refuse(404, "Not found")
    if not event["out"]:
        return refuse(401, "Not connected")
    if call == "GET user/info":
        return [{"reply": {"data": {"id": event["out"], "name": "Yo"}}}]
    if call == f"POST triggers/{TRIGGER}":
        return [{"reply": {"data": yos(event)}}]
    fields = event["body"].get("actionFields")
    if not isinstance(fields, dict):
        return refuse(400, "No actionFields")
    url = fields.get("photo_url")
    if url is not None and not isinstance(url, str):
        return refuse(400, "photo_url: text", status="SKIP")
    send = {"send": "picture", "url": url} if url else {"send": "yo"}
    return [send, {"reply": {"data": [{"id": event["id"]}]}}]


event = json.load(sys.stdin)

if event["trigger"] == "webhook":
    answer = called(event)
elif event["out"] and not event["group"]:     # a connected user Yoed IFTTT
    answer = [{"call": "https://realtime.ifttt.com/v1/notifications", "body": {"data": [{"user_id": event["out"]}]}}]
else:
    answer = []

print(json.dumps(answer))
