"""IFTTT's own API (https://ifttt.com/docs/api_reference): "You Yo IFTTT" runs an Applet, "Yo me" Yos its user.

IFTTT takes no Yo from us: it is told there is one, then asks for it.
"""
import json
import sys
from datetime import datetime, timezone

TRIGGER, ACTION = "you_yo_ifttt", "yo_me"


def yos(event):
    """The user's Yos to IFTTT, newest first."""
    sent = event["yos"]
    if event["out"] == "test":                # IFTTT's own tests want three
        sent = [{"id": f"test{n}", "kind": "yo", "at": 1_700_000_000 + n} for n in (3, 2, 1)]
    limit = event["body"].get("limit")
    if type(limit) is not int or limit < 0:
        limit = 50
    return [{
        "received_at": datetime.fromtimestamp(yo["at"], timezone.utc).isoformat(),
        "kind": yo["kind"],
        "meta": {"id": yo["id"], "timestamp": yo["at"]},
    } for yo in sent[:limit]]


def called(event):
    """IFTTT calls us."""
    call = event["method"] + " " + event["path"].removeprefix("v1/")
    if call == "GET status":
        return [{"reply": {}}]
    if call == "POST test/setup" and event["test"]:
        samples = {"triggers": {TRIGGER: {}}, "actions": {ACTION: {}}}
        return [{"reply": {"data": {"accessToken": event["test"], "samples": samples}}}]
    if call.startswith(f"DELETE triggers/{TRIGGER}/trigger_identity/"):
        return [{"reply": {}}]
    if event["out"] and call == "GET user/info":
        return [{"reply": {"data": {"id": event["out"], "name": "Yo"}}}]
    if event["out"] and call == f"POST triggers/{TRIGGER}":
        return [{"reply": {"data": yos(event)}}]
    if event["out"] and call == f"POST actions/{ACTION}":
        return [{"send": "yo"}, {"reply": {"data": [{"id": event["id"]}]}}]
    return [{"reply": {"errors": [{"message": "Not found"}]}, "status": 404}]


event = json.load(sys.stdin)

if event["trigger"] == "webhook":
    answer = called(event)
elif event["out"] and not event["group"]:     # a connected user Yoed IFTTT
    answer = [{"call": "https://realtime.ifttt.com/v1/notifications", "body": {"data": [{"user_id": event["out"]}]}}]
else:
    answer = []

print(json.dumps(answer))
