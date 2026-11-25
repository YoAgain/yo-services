"""Started anew for every event: one JSON object comes in, one JSON list goes out."""
import base64
import io
import json
import sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont


def clock(now):
    """The time as a JPEG."""
    image = Image.new("RGB", (1080, 1080), "#9B59B6")
    font = ImageFont.load_default(360)
    ImageDraw.Draw(image).text((540, 540), f"{now:%H:%M}", font=font, fill="white", anchor="mm")
    jpeg = io.BytesIO()
    image.save(jpeg, "JPEG")
    return base64.b64encode(jpeg.getvalue()).decode()


event = json.load(sys.stdin)

if event["trigger"] == "cron":          # the reminder is due
    answer = [{"send": "yo"}]
elif event["trigger"] == "webhook":     # called: a Yo to the user whose secret it carried, and a reply
    answer = [{"send": "yo"}, {"reply": {"ok": True}}] if event["out"] else [{"reply": {}}]
elif event["kind"] != "yo":             # a picture or a video came: back it goes
    answer = [{"send": event["kind"], "media": event["media"]}]
elif event["group"]:                    # in a group nobody is reminded
    answer = [{"send": "yo"}]
else:
    answer = [
        {"send": "picture", "jpeg": clock(datetime.fromtimestamp(event["now"]))},
        {"remind": event["now"] + 600},
    ]
    if event["out"]:                    # connected: the other side hears of the Yo
        answer.append({"call": "https://example.com/yo", "body": {"user": event["out"]}})

print(json.dumps(answer))
