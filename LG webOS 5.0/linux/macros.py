"""Daily TV power rules, with injectable clocks and asynchronous transport."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

from network import local_host


def minutes(value, end=False):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError("Use 24-hour times, such as 21:00 and 24:00.")
    hour, minute = map(int, value.split(":"))
    if end and hour == 24 and minute == 0:
        return 1440
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError("Hours must be 00–23. Use 24:00 only for the end of the day.")
    return hour * 60 + minute


@dataclass(frozen=True)
class AutoOffRule:
    enabled: bool = False
    host: str = ""
    start: str = "21:00"
    end: str = "24:00"
    repeat: bool = True
    warn_before_off: bool = True
    paused_on: str = ""
    handled_window: str = ""
    warning_window: str = ""
    warning_due: float = 0

    def validate(self):
        start, end = minutes(self.start), minutes(self.end, end=True)
        if start == end:
            raise ValueError("Start and end must be different.")
        if any(type(value) is not bool for value in (self.enabled, self.repeat, self.warn_before_off)):
            raise ValueError("Invalid macro switches.")
        if not isinstance(self.host, str) or (self.enabled and not local_host(self.host)):
            raise ValueError("Choose a TV in Settings before enabling this macro.")
        for value in (self.paused_on, self.handled_window, self.warning_window):
            if not isinstance(value, str):
                raise ValueError("Invalid saved macro state.")
        if type(self.warning_due) not in (int, float) or not math.isfinite(self.warning_due) or self.warning_due < 0:
            raise ValueError("Invalid saved warning countdown.")
        if self.paused_on:
            datetime.strptime(self.paused_on, "%Y-%m-%d")
        return self

    def window(self, now):
        """Identity of this occurrence; start inclusive, end exclusive, local time."""
        start, end = minutes(self.start), minutes(self.end, end=True)
        minute = now.hour * 60 + now.minute
        day = now.date()
        if start < end:
            if not start <= minute < end:
                return None
        else:
            if minute < end:
                day -= timedelta(days=1)
            elif minute < start:
                return None
        return f"{day.isoformat()}|{self.host}|{self.start}|{self.end}"

    def eligible(self, now):
        window = self.window(now)
        return (self.enabled and self.paused_on != now.date().isoformat() and window is not None
                and (self.repeat or self.handled_window != window))

    def watch_window(self, now):
        window = self.window(now)
        if window is None and self.warn_before_off:
            window = self.window(now + timedelta(seconds=60))
        return window

    def watching(self, now):
        window = self.watch_window(now)
        return (self.enabled and self.paused_on != now.date().isoformat() and window is not None
                and (self.repeat or self.handled_window != window))


class MacroStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path(os.environ.get(
            "XDG_CONFIG_HOME", Path.home() / ".config")) / "lgwebos-menubar")
        self.path = self.directory / "macros.json"

    def load(self):
        try:
            value = json.loads(self.path.read_text())
            return AutoOffRule(**value).validate()
        except FileNotFoundError:
            return AutoOffRule()
        except (OSError, ValueError, TypeError) as error:
            raise RuntimeError("Cannot read the saved macro. Review and save the rule again.") from error

    def save(self, rule):
        rule.validate()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".macros-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(asdict(rule), stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


class AutoOffEngine:
    INTERVAL = 10

    def __init__(self, rule, make_client, persist, notify, now=None, monotonic=None):
        self.rule = rule.validate()
        self.make_client, self.persist, self.notify = make_client, persist, notify
        self.now = now or (lambda: datetime.now().astimezone())
        self.monotonic = monotonic or time.monotonic
        self.client = None
        self.generation = 0
        self.pending = False
        self.next_check = 0
        self.started = 0
        self.blocked = False
        self.stopped = False
        self.last_action = ""
        self.status = ""
        self.warning_monotonic = self.monotonic() + max(0, rule.warning_due - self.now().timestamp())

    def report(self, message):
        self.status = message
        self.notify(message)

    def close_client(self):
        self.generation += 1
        client, self.client = self.client, None
        self.pending = False
        if client:
            client.close()

    def configure(self, rule):
        self.close_client()
        self.rule = rule.validate()
        self.blocked = False
        self.next_check = 0
        self.tick()

    def tick(self):
        if self.stopped:
            return False
        now = self.now()
        if not self.rule.watching(now):
            if self.client:
                self.close_client()
            if not self.rule.enabled:
                self.report("Off · Enable and save the rule to start.")
            elif self.rule.paused_on == now.date().isoformat():
                self.report("Paused for today · Resumes automatically at midnight.")
            elif self.rule.window(now) and not self.rule.repeat:
                self.report("Done for this time window · Watching again next time.")
            else:
                self.report(f"Scheduled daily · {self.rule.start}–{self.rule.end} (local time)")
            return True
        if self.blocked:
            return True
        clock = self.monotonic()
        if self.client and (not self.client.ready or self.pending) and clock - self.started >= 20:
            self.close_client()
            self.next_check = clock + self.INTERVAL
            self.report("TV not responding · Retrying automatically.")
        if self.pending or clock < self.next_check:
            return True
        if not self.client or self.client.closed:
            self.close_client()
            self.started = clock
            self.next_check = clock + self.INTERVAL
            generation = self.generation
            self.client = self.make_client(self.rule.host, lambda text: self.connection_state(generation, text))
            self.report("Checking TV · Reconnecting automatically if needed.")
            self.client.connect(background=True)
        elif self.client.ready:
            self.check_power()
        return True

    def current(self, generation):
        return (not self.stopped and generation == self.generation and self.client is not None
                and self.rule.watching(self.now()))

    def connection_state(self, generation, message):
        if not self.current(generation):
            return
        if self.client.ready:
            self.check_power()
        elif self.client.closed:
            if getattr(self.client, "background_blocked", False):
                self.blocked = True
                self.report("Pairing needs attention · Connect TV manually, then save this macro again.")
            else:
                self.report("Waiting for TV · Will check again automatically.")

    def check_power(self):
        if self.pending or not self.rule.watching(self.now()):
            return
        generation = self.generation
        self.pending = True
        self.started = self.monotonic()
        self.next_check = self.started + self.INTERVAL

        def received(data, error):
            if not self.current(generation):
                return
            self.pending = False
            if error:
                self.report("Cannot read TV power state · Will retry; no power-off sent.")
                return
            state = str(data.get("state", "")).casefold()
            if state != "active":
                self.report("Watching · Waiting for the TV to become active.")
                return
            self.prepare_off(generation)

        self.client.request("com.webos.service.tvpower/power/getPowerState", callback=received)

    def prepare_off(self, generation):
        if not self.current(generation):
            return
        now = self.now()
        window = self.rule.watch_window(now)
        if self.rule.warn_before_off and self.rule.handled_window != window:
            if self.rule.warning_window != window:
                self.warn(generation, window)
                return
            remaining = max(self.rule.warning_due - now.timestamp(), self.warning_monotonic - self.monotonic())
            if remaining > 0:
                self.report(f"TV warned · First power-off in {math.ceil(remaining)} seconds. Pause today to cancel.")
                return
        if self.rule.eligible(now):
            self.turn_off(generation)

    def warn(self, generation, window):
        if self.rule.window(self.now() + timedelta(seconds=60)) != window:
            self.report("Less than a minute remains · No first power-off in this window.")
            return
        self.pending = True
        self.started = self.monotonic()

        def notified(data, error):
            if not self.current(generation):
                return
            self.pending = False
            if error:
                self.blocked = "Disconnected" not in error and "too long" not in error
                self.report("TV warning not confirmed · No power-off sent. Check notification support or disable the warning.")
                return
            marked = replace(self.rule, warning_window=window, warning_due=self.now().timestamp() + 60)
            try:
                self.persist(marked)
                self.rule = marked
            except Exception:
                self.blocked = True
                self.report("Cannot save warning countdown · No power-off sent. Save the rule to retry.")
                return
            self.warning_monotonic = self.monotonic() + 60
            self.report("TV warned · First power-off in 60 seconds. Pause today to cancel.")

        self.client.request("system.notifications/createToast",
                            {"message": "This TV will turn off automatically in 1 minute. To cancel, pause today's macro in LG webOS Remote."},
                            callback=notified)

    def turn_off(self, generation):
        # Re-evaluate after every async boundary: pause, midnight or editing may have intervened.
        if not self.current(generation) or not self.rule.eligible(self.now()):
            return
        window = self.rule.window(self.now())
        previous = self.rule
        marked = replace(previous, handled_window=window)
        try:
            # Persist before dispatch: a TV often closes its socket before acknowledging power-off.
            # This prevents a once-only rule firing twice after a restart or a lost acknowledgement.
            self.persist(marked)
            self.rule = marked
        except Exception:
            self.blocked = True
            self.report("Cannot save macro history · No power-off sent. Save the rule to retry.")
            return
        self.pending = True
        self.started = self.monotonic()
        self.last_action = self.now().strftime("%H:%M:%S")
        self.report(f"Power-off sent at {self.last_action} · " +
                    ("Will turn off again if switched back on." if self.rule.repeat else "Once for this time window."))

        def sent(data, error):
            if generation != self.generation or self.stopped:
                return
            self.pending = False
            # Explicit permission errors are visible; ambiguous network loss does not resend a once-only command.
            if error and "Disconnected" not in error and "too long" not in error:
                try:
                    self.persist(previous)
                    self.rule = previous
                except Exception:
                    pass
                self.blocked = True
                self.report("Power-off rejected. Save the macro to retry: " + str(error))

        self.client.request("system/turnOff", callback=sent)

    def stop(self):
        self.stopped = True
        self.close_client()
