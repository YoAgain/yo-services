import json
import sys

event = json.load(sys.stdin)
print(json.dumps([{"send": event["kind"], "media": event["media"]}]))
