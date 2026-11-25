import json
import random
from pathlib import Path

pictures = [path.name for path in (Path(__file__).parent / "assets").glob("*.jpg")]
print(json.dumps([
    {"wait_ms": random.randint(1000, 3000)},
    {"send": "picture", "file": random.choice(pictures)},
]))
