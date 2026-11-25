"""`python3 test.py`: every service, and that this test catches bad ones. (Some need Pillow.)"""
import ast
import base64
import itertools
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICES = [HERE / "template/template.py", *sorted(p.with_suffix(".py") for p in HERE.glob("*/*/*.toml"))]
FIELDS = {"names": list, "about": str, "triggers": list}
BRIDGE = {"return_url": str, "call_urls": list, "key_header": str}
NOW = 1_800_000_000
JPEG, MAX_PICTURE, MAX_ANSWER = b"\xff\xd8\xff", 512 * 1024, 1024 * 1024

IMPORTS = {"base64", "datetime", "io", "json", "math", "pathlib", "random", "sys", "zoneinfo", "PIL"}
NAMES = {"__import__", "breakpoint", "compile", "delattr", "eval", "exec", "getattr", "globals", "input", "locals",
         "memoryview", "open", "setattr", "vars"}
SYS = {"stdin"}
WRITES = {"chmod", "hardlink_to", "mkdir", "open", "rename", "replace", "rmdir", "symlink_to", "touch", "unlink",
          "write_bytes", "write_text"}
CANARY = "canary-5c1f"


class Bad(Exception):
    pass


def need(true, why):
    if not true:
        raise Bad(why)


def settings(path):
    """Its TOML, as the server reads it."""
    try:
        toml = tomllib.loads(path.with_suffix(".toml").read_text())
    except (OSError, ValueError):
        raise Bad("no TOML") from None
    bridge = toml.pop("bridge", None)
    need({k: type(v) for k, v in toml.items()} == FIELDS, "the fields, no more")
    names = toml["names"]
    need(names and all(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._]{1,32}", name) for name in names), "names")
    need(len({name.lower() for name in names}) == len(names), "a name twice")
    need(toml["triggers"] and set(toml["triggers"]) <= {"yo", "cron"}, "triggers")
    toml["bridge"] = bridge
    if bridge is not None:
        need(isinstance(bridge, dict) and {k: type(v) for k, v in bridge.items()} == BRIDGE, "bridge: all of it, no more")
        need(re.fullmatch(r"https://[a-z0-9-]+(\.[a-z0-9-]+)+(/[A-Za-z0-9._-]+)+", bridge["return_url"]), "return_url")
        need(all(isinstance(url, str) and re.fullmatch(r"https://[a-z0-9-]+(\.[a-z0-9-]+)+/([A-Za-z0-9._-]+/)*", url)
                 for url in bridge["call_urls"]), "call_urls")
        need(re.fullmatch(r"[A-Za-z0-9-]{1,64}", bridge["key_header"]), "key_header")
    return toml


def read(source):
    """What can be seen without running it: nothing that reaches outside, or hides that it does."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            need({a.name.split(".")[0] for a in node.names} <= IMPORTS, "import")
            need(not any(a.asname for a in node.names), "import under another name")
        elif isinstance(node, ast.ImportFrom):
            need(node.level == 0 and node.module.split(".")[0] in IMPORTS, "import")
            need(node.module != "sys" and all(a.name != "*" for a in node.names), "import")
        elif isinstance(node, ast.Name):
            need(node.id not in NAMES and not node.id.startswith("__") or node.id == "__file__", f"name {node.id}")
        elif isinstance(node, ast.Attribute):
            need(not node.attr.startswith("_"), f"attribute {node.attr}")
            need(node.attr not in WRITES or isinstance(node.value, ast.Constant) or node.attr == "replace", f"{node.attr}")
            if isinstance(node.value, ast.Name) and node.value.id == "sys":
                need(node.attr in SYS, f"sys.{node.attr}")
        elif isinstance(node, ast.While):
            need(not isinstance(node.test, ast.Constant), "an endless loop")
        elif isinstance(node, ast.ExceptHandler):
            need(node.type is not None, "an except for everything")
    need(not re.search(r"[^\x09\x0a\x20-\x7e\u00a0-\u024f·]", source), "a character that hides something")


# Runs a service with Python's own events watched: what opens a socket, starts a process or writes a file ends it.
WATCH = """
import os, runpy, sys
def watch(event, args):
    if event.split(".")[0] in {"socket", "subprocess", "ctypes", "shutil", "ftplib", "urllib", "pty"} or event in {
            "os.system", "os.exec", "os.fork", "os.posix_spawn", "os.remove", "os.rename", "os.mkdir", "os.chmod",
            "os.symlink", "os.link", "os.kill", "os.truncate"}:
        os.write(2, b"WATCH " + event.encode()); os._exit(99)
    if event == "open" and (isinstance(args[1], str) and set(args[1]) & set("wax+") or (args[2] or 0) & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
        os.write(2, b"WATCH write"); os._exit(99)
    if event == "open" and str(args[0]).startswith(("/etc/passwd", "/home/", "/root", "/proc/self/environ", "/var")):
        if not str(args[0]).startswith(sys.argv[2]) and "site-packages" not in str(args[0]) and not str(
                args[0]).startswith((sys.prefix, sys.base_prefix)):
            os.write(2, b"WATCH read"); os._exit(99)
sys.addaudithook(watch)
sys.argv[0] = sys.argv[1]
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


def locked_in(folder):
    """bubblewrap around all that (a CI machine is thrown away anyway): no network, nothing to see but Python and the service."""
    if not shutil.which("bwrap"):
        need("CI" in os.environ, "install bubblewrap: no unknown script runs on your own machine without it")
        return []
    seen = {"/usr", "/lib", "/lib64", "/etc/ld.so.cache", sys.prefix, sys.base_prefix, str(folder)}
    binds = [part for path in sorted(seen) if Path(path).exists() for part in ("--ro-bind", path, path)]
    return ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--proc", "/proc", "--dev", "/dev", *binds]


def run(path, event):
    command = [*locked_in(path.parent), sys.executable, "-I", "-B", "-c", WATCH, str(path), str(path.parent)]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          preexec_fn=limits, env={"SECRET": CANARY}) as process:
        slow = threading.Timer(15, process.kill)
        slow.start()
        try:
            process.stdin.write(json.dumps(event).encode())
            process.stdin.close()
        except BrokenPipeError:
            pass
        said = process.stdout.read(MAX_ANSWER + 1)
        process.stdout.close()
        if len(said) > MAX_ANSWER:
            process.kill()
        code = process.wait()
        slow.cancel()
    need(len(said) <= MAX_ANSWER, "says too much")
    need(code == 0, f"ended with {code}: {said[-200:]!r}")
    need(CANARY.encode() not in said, "tells its environment")
    try:
        return json.loads(said)
    except ValueError:
        raise Bad("no JSON") from None


def check(action, event, toml, folder):
    """One action, as strictly as the gatekeeper."""
    need(isinstance(action, dict), "no action")
    action = {k: v for k, v in action.items() if v is not None}
    keys, sends = set(action), action.get("send")
    if keys == {"send"}:
        need(sends == "yo" and (event["trigger"] != "webhook" or event["out"]), "send")
    elif keys == {"send", "media"}:
        need(sends == event["kind"] and event["media"] and action["media"] == event["media"], "not what came")
    elif keys == {"send", "jpeg"}:
        try:
            jpeg = base64.b64decode(action["jpeg"], validate=True)
        except (TypeError, ValueError):
            raise Bad("jpeg") from None
        need(sends == "picture" and jpeg.startswith(JPEG) and len(jpeg) <= MAX_PICTURE, "jpeg")
    elif keys == {"send", "file"}:
        need(sends == "picture" and isinstance(action["file"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.jpg", action["file"]), "file")
        picture = folder / action["file"]
        need(picture.is_file() and not picture.is_symlink() and picture.stat().st_size <= MAX_PICTURE, "file")
        need(picture.read_bytes().startswith(JPEG), "file")
    elif keys == {"send", "url"}:
        need(sends == "picture" and event["trigger"] == "webhook" and event["out"], "url")
        need(isinstance(action["url"], str) and len(action["url"]) <= 2048, "url")
    elif keys == {"wait_ms"}:
        need(type(action["wait_ms"]) is int and 0 <= action["wait_ms"] <= 5000, "wait_ms")
    elif keys == {"remind"}:
        need("cron" in toml["triggers"] and event["trigger"] == "yo" and not event["group"] and type(action["remind"]) is int
             and NOW + 60 <= action["remind"] <= NOW + 400 * 86400, "remind")
    elif keys == {"forget"}:
        need("cron" in toml["triggers"] and not event["group"] and action["forget"] is True, "forget")
    elif keys in ({"reply"}, {"reply", "status"}):
        need(type(action.get("status", 200)) is int and 200 <= action.get("status", 200) < 600, "status")
        need(event["trigger"] == "webhook" and isinstance(action["reply"], (dict, list)), "reply")
        need(len(json.dumps(action["reply"])) <= 64 * 1024, "reply")
    elif keys == {"call", "body"}:
        need(event["out"] and isinstance(action["call"], str) and isinstance(action["body"], dict), "call")
        below = [action["call"][len(url):] for url in toml["bridge"]["call_urls"] if action["call"].startswith(url)]
        need(any(re.fullmatch(r"[A-Za-z0-9._/-]*", rest) and ".." not in rest for rest in below), "call")
        need(len(json.dumps(action["body"])) <= 64 * 1024, "call")
    else:
        raise Bad(f"an action there is not: {sorted(keys)}")


def events(toml):
    for name, trigger in itertools.product(toml["names"], toml["triggers"] + ["webhook"] * bool(toml["bridge"])):
        for kind in (trigger,) if trigger in ("cron", "webhook") else ("yo", "picture", "video"):
            for group in (False,) if trigger in ("cron", "webhook") else (False, True):
                for remembered in (False, True) if "cron" in toml["triggers"] else (False,):
                    for out in (None, "OUT") if toml["bridge"] else (None,):
                        call = {"id": "CALL", "method": "POST", "path": "a/b", "body": {}, "yos": [], "test": None}
                        yield {"name": name, "trigger": trigger, "kind": kind, "group": group, "remembered": remembered,
                               "media": "it" if kind in ("picture", "video") else None, "now": NOW, "out": out,
                               **{k: v if trigger == "webhook" else None for k, v in call.items()}}


def prove(path):
    """A service, all of it: raises Bad."""
    toml = settings(path)
    need(toml["names"][0].lower() == path.stem and path.parent.name == path.stem, "folder and files are named after the bot")
    need(path.exists(), "no script")
    read(path.read_text())
    for event in events(toml):
        before = sorted(path.parent.rglob("*"))
        answer = run(path, event)
        need(sorted(path.parent.rglob("*")) == before, "leaves files")
        need(isinstance(answer, list) and len(answer) <= 4, "a list of few actions")
        for action in answer:
            check(action, event, toml, path.parent / "assets")
        need(sum("send" in action for action in answer) <= 1, "sends too much")
        need(sum("reply" in action for action in answer) <= 1, "replies twice")
        need(sum("call" in action for action in answer) <= 1, "calls twice")
        need(sum("remind" in action for action in answer) <= 1, "more than one reminder")
        need(sum(action.get("wait_ms") or 0 for action in answer) <= 5000, "waits too long")


class Services(unittest.TestCase):
    def test_every_service(self):
        for path in SERVICES:
            with self.subTest(path.name):
                prove(path)

    def test_nothing_else_lies_around(self):
        folders = {path.parent for path in SERVICES}
        for folder in [HERE / "template", *(f for f in HERE.glob("*/*") if f.is_dir() and not f.parts[-2].startswith("."))]:
            with self.subTest(folder.name):
                self.assertIn(folder, folders)
                names = {f.name for f in folder.iterdir()} - {"assets", "README.md", "logo.png", "applet-logo.svg"}
                self.assertEqual(names, {f"{folder.name}.toml", f"{folder.name}.py"})

    def test_ping_sends_back_what_came(self):
        ping = HERE / "yo/ping/ping.py"
        for event in [*events(settings(ping)), {"kind": "probe", "media": None}]:
            self.assertEqual(run(ping, event), [{"send": event["kind"], "media": event["media"]}])

    def test_ifttt(self):
        ifttt = HERE / "partner/ifttt/ifttt.py"
        toml = settings(ifttt)
        yos = [{"id": "2", "kind": "picture", "at": NOW}, {"id": "1", "kind": "yo", "at": NOW - 60}]
        base = {"name": "IFTTT", "trigger": "webhook", "kind": "webhook", "media": None, "group": False, "remembered": False,
                "now": NOW, "id": "CALL", "body": {}, "out": "OUT", "yos": yos, "test": None}

        def ask(call, **more):
            method, path = call.split(" ")
            event = {**base, "method": method, "path": "v1/" + path, **more}
            answer = run(ifttt, event)
            for action in answer:
                check(action, event, toml, ifttt.parent)
            return answer

        def ids(**body):
            return [yo["meta"]["id"] for yo in ask("POST triggers/you_yo_ifttt", body=body)[0]["reply"]["data"]]

        self.assertEqual(ask("GET status", out=None), [{"reply": {}}])
        self.assertEqual(ids(), ["2", "1"])
        self.assertEqual(ids(limit=1), ["2"])
        self.assertEqual(ids(limit=0), [])
        self.assertEqual(ask("POST actions/yo_me"), [{"send": "yo"}, {"reply": {"data": [{"id": "CALL"}]}}])
        photo = ask("POST actions/yo_me", body={"actionFields": {"photo_url": "https://example.com/a.jpg"}})[0]
        self.assertEqual(photo, {"send": "picture", "url": "https://example.com/a.jpg"})
        self.assertEqual(ask("GET user/info")[0]["reply"]["data"], {"id": "OUT", "name": "Yo"})
        self.assertEqual(ask("POST test/setup", out=None, test="T")[0]["reply"]["data"]["accessToken"], "T")
        self.assertEqual(ask("DELETE triggers/you_yo_ifttt/trigger_identity/x", out=None), [{"reply": {}}])
        for call in ("GET user/info", "POST triggers/you_yo_ifttt", "POST actions/yo_me", "POST test/setup"):
            self.assertEqual(ask(call, out=None)[0]["status"], 404)
        yo = {**base, "trigger": "yo", "kind": "yo"}
        self.assertEqual(run(ifttt, yo)[0]["body"], {"data": [{"user_id": "OUT"}]})
        self.assertEqual(run(ifttt, {**yo, "out": None}), [])
        self.assertEqual(run(ifttt, {**yo, "group": True}), [])

    def test_no_names_of_people_or_machines(self):
        for path in SERVICES:
            text = path.read_text() + path.with_suffix(".toml").read_text()
            self.assertNotRegex(text, r"\b[0-9a-f]{32}\b|/home/|\b\d+\.\d+\.\d+\.\d+\b")


GOOD = (HERE / "yo/ping/ping.py").read_text()
TOML = 'names = ["PING", "PINGTEST"]\nabout = "a"\ntriggers = ["yo", "cron"]\n'
SAY = "import json, sys\nevent = json.load(sys.stdin)\nprint(json.dumps(%s))\n"
EVIL = {
    "network": "import socket\n",
    "process": "import subprocess\n",
    "system": "import os\nos.system('id')\n",
    "hidden import": "__import__('os').system('id')\n",
    "eval": "eval('1')\n",
    "builtins": "print(__builtins__)\n",
    "class climbing": "print(().__class__.__base__.__subclasses__())\n",
    "sys.modules": "import sys\nsys.modules['os'].system('id')\n",
    "from sys": "from sys import modules\n",
    "another name": "import sys as s\n",
    "star": "from json import *\n",
    "a module's module": "import pathlib\npathlib.os.system('id')\n",
    "through json": "import json\njson.codecs.sys.modules\n",
    "open": "print(open('/etc/passwd').read())\n",
    "read": "from pathlib import Path\nprint(Path('/etc/passwd').read_text())\n",
    "write": "from pathlib import Path\nPath('x').write_text('x')\n",
    "environment": "from pathlib import Path\nprint(Path('/proc/self/environ').read_text())\n",
    "endless": "while True:\n    pass\n",
    "endless, hidden": "x = 1\nwhile x:\n    pass\n",
    "memory": "x = 'x' * (1 << 31)\n",
    "flood": "print('x' * (1 << 22))\n",
    "noise": "import json, sys\nprint('x', file=sys.stderr)\nprint('[]')\n",
    "bare except": "try:\n    pass\nexcept:\n    pass\n",
    "bidi": "x = '\u202e'\nprint('[]')\n",
    "crash": "1 / 0\n",
    "no answer": "pass\n",
    "to another": SAY % '[{"send": "yo", "to": "x"}]',
    "other media": SAY % '[{"send": "picture", "media": "other"}]',
    "a user": SAY % '[{"remind": event["now"]}]',
    "a path": SAY % '[{"send": "picture", "file": "../ping.py"}]',
    "a website": SAY % '[{"call": "https://example.com"}]',
    "too much": SAY % '[{"send": "yo"}] * 2',
    "a series": SAY % '[{"remind": event["now"] + 60}] if event["trigger"] == "cron" else []',
    "soon": SAY % '[{"remind": event["now"] + 1}]',
    "no text": SAY % '[{"send": "picture", "jpeg": 1}]',
    "long waits": SAY % '[{"wait_ms": 4000}, {"wait_ms": 4000}]',
    "a reply to a Yo": SAY % '[{"reply": {}}]',
    "a call unconnected": SAY % '[{"call": "https://example.com/", "body": {}}]',
    "not a picture": SAY % '[{"send": "picture", "jpeg": "AAAA"}]',
}
TOMLS = {
    "missing": ("about", "abou"), "extra": ("about", "root = 1\nabout"), "no TOML": ("about", "print(1)\nabout"),
    "internet": ("triggers", 'allowed_urls = ["https://example.com/"]\ntriggers'), "trigger": ('"yo"', '"root"'),
    "webhook": ('"yo"', '"webhook"'), "half bridge": ("triggers", 'bridge = {return_url = "https://example.com/a"}\ntriggers'),
    "bridge to http": ("triggers", 'bridge = {return_url = "http://example.com/a", call_urls = [], key_header = "A"}\ntriggers'),
    "name": ('"PING"', '"YOGPT"'), "no name": ('"PING", "PINGTEST"', ""), "twice": ('"PINGTEST"', '"ping"'),
    "one name": ('["PING", "PINGTEST"]', '"PING"'), "type": ('"a"', "1"),
}


class ThisTest(unittest.TestCase):
    """The test itself: a good service passes, each bad one does not."""

    def make(self, code, toml=TOML):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "ping/ping.py"
        path.parent.mkdir()
        path.write_text(code)
        path.with_suffix(".toml").write_text(toml)
        return path

    def test_good(self):
        prove(self.make(GOOD, TOML.replace(', "cron"', "")))

    def test_evil_is_caught(self):
        for name, code in EVIL.items():
            with self.subTest(name), self.assertRaises((Bad, SyntaxError)):
                prove(self.make(code))

    def test_evil_is_caught_while_running_too(self):
        """What reading did not see, running does."""
        more = {"network": "socket.socket()\n", "process": "subprocess.run(['id'])\n"}
        for name in ("network", "process", "system", "hidden import", "open", "read", "write", "environment", "memory"):
            with self.subTest(name), self.assertRaises(Bad):
                run(self.make(EVIL[name] + more.get(name, "")), {"kind": "yo"})

    def test_calls_stay_below_call_urls(self):
        toml = {"bridge": {"call_urls": ["https://example.com/a/"]}, "triggers": ["yo"]}
        event = {"trigger": "yo", "out": "OUT", "group": False}
        check({"call": "https://example.com/a/b", "body": {}}, event, toml, HERE)
        for url in ("https://example.com/b", "https://example.com/a/../b", "https://example.com/a/?x", "https://evil.com/a/"):
            with self.subTest(url), self.assertRaises(Bad):
                check({"call": url, "body": {}}, event, toml, HERE)
        with self.assertRaises(Bad):
            check({"call": "https://example.com/a/b", "body": {}}, {**event, "out": None}, toml, HERE)

    def test_bad_tomls_are_caught(self):
        for name, (old, new) in TOMLS.items():
            self.assertIn(old, TOML, name)
            with self.subTest(name), self.assertRaises(Bad):
                prove(self.make(GOOD, TOML.replace(old, new, 1)))


if __name__ == "__main__":
    unittest.main()
