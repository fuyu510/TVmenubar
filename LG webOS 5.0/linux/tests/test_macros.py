from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macros import AutoOffEngine, AutoOffRule, MacroStore

HOST = ".".join(map(str, (10, 0, 0, 2)))


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.rule = AutoOffRule(enabled=True, host=HOST)

    def test_default_rule_is_disabled(self):
        self.assertFalse(AutoOffRule().enabled)
        self.assertTrue(AutoOffRule().repeat)

    def test_start_inclusive_and_midnight_exclusive(self):
        for value, expected in (("2026-10-25T20:59:59", False), ("2026-10-25T21:00:00", True),
                                ("2026-10-25T23:59:59", True), ("2026-10-26T00:00:00", False)):
            self.assertEqual(self.rule.eligible(datetime.fromisoformat(value)), expected)

    def test_overnight_window_has_one_identity(self):
        rule = replace(self.rule, start="22:00", end="02:00")
        start = datetime(2026, 10, 25, 23)
        early = datetime(2026, 10, 26, 1)
        self.assertEqual(rule.window(start), rule.window(early))
        self.assertFalse(rule.eligible(datetime(2026, 10, 26, 2)))
        self.assertFalse(rule.eligible(datetime(2026, 10, 26, 21)))

    def test_pause_expires_at_calendar_midnight_even_for_overnight_rule(self):
        rule = replace(self.rule, end="02:00", paused_on="2026-10-25")
        self.assertFalse(rule.eligible(datetime(2026, 10, 25, 23)))
        self.assertTrue(rule.eligible(datetime(2026, 10, 26, 0)))

    def test_once_per_window_rearms_next_day(self):
        now = datetime(2026, 10, 25, 21)
        rule = replace(self.rule, repeat=False, handled_window=self.rule.window(now))
        self.assertFalse(rule.eligible(now))
        self.assertTrue(rule.eligible(now + timedelta(days=1)))

    def test_invalid_times_and_hosts(self):
        for changes in ({"start": "24:00"}, {"end": "24:01"}, {"end": "21:00"},
                        {"start": "9:00"}, {"end": "22:60"}, {"host": "example.com"}, {"enabled": "true"}):
            with self.assertRaises(ValueError):
                replace(self.rule, **changes).validate()

    def test_pause_and_completion_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            rule = replace(self.rule, repeat=False, paused_on="2026-10-25", handled_window="mock-window")
            MacroStore(directory).save(rule)
            self.assertEqual(MacroStore(directory).load(), rule)
            self.assertEqual(MacroStore(directory).path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_file_does_not_enable_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(directory)
            store.path.write_text('{"enabled": "yes"}')
            with self.assertRaises(RuntimeError):
                store.load()


class FakeClient:
    def __init__(self, host, state):
        self.host, self.state = host, state
        self.ready = self.closed = False
        self.background_blocked = False
        self.calls = []
        self.background = None

    def connect(self, background=False):
        self.background = background

    def connected(self):
        self.ready = True
        self.state("Connected")

    def request(self, uri, payload=None, callback=None):
        self.calls.append((uri, callback))

    def reply(self, data, error=None):
        self.calls[-1][1](data, error)

    def close(self):
        self.closed, self.ready = True, False


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.clock = datetime(2026, 10, 25, 21)
        self.elapsed = 100.0
        self.clients, self.saved, self.messages = [], [], []
        self.rule = AutoOffRule(enabled=True, host=HOST, warn_before_off=False)
        self.engine = self.make_engine(self.rule)

    def make_engine(self, rule):
        def factory(host, state):
            client = FakeClient(host, state)
            self.clients.append(client)
            return client
        return AutoOffEngine(rule, factory, self.saved.append, self.messages.append,
                             now=lambda: self.clock, monotonic=lambda: self.elapsed)

    def connect(self):
        self.engine.tick()
        client = self.clients[-1]
        client.connected()
        return client

    def advance(self, seconds=11):
        self.clock += timedelta(seconds=seconds)
        self.elapsed += seconds

    def off_calls(self):
        return [call for client in self.clients for call in client.calls if call[0] == "system/turnOff"]

    def test_only_active_tv_is_turned_off(self):
        client = self.connect()
        self.assertTrue(client.background)
        client.reply({"state": "Standby"})
        self.assertEqual(self.off_calls(), [])
        self.advance()
        self.engine.tick()
        client.reply({"state": "Active"})
        self.assertEqual(len(self.off_calls()), 1)

    def test_repeat_option_reconnects_and_turns_off_again(self):
        client = self.connect()
        client.reply({"state": "Active"})
        client.reply({"returnValue": True})
        client.close()
        self.advance()
        self.engine.tick()
        second = self.clients[-1]
        self.assertIsNot(second, client)
        second.connected()
        second.reply({"state": "Active"})
        self.assertEqual(len(self.off_calls()), 2)

    def test_once_option_survives_lost_ack_and_app_restart(self):
        self.engine.configure(replace(self.rule, repeat=False))
        client = self.clients[-1]
        client.connected()
        client.reply({"state": "Active"})
        self.assertEqual(len(self.saved), 1)
        restarted = self.make_engine(self.saved[-1])
        restarted.tick()
        self.assertEqual(len(self.clients), 1)
        self.advance(24 * 60 * 60)
        restarted.tick()
        self.assertEqual(len(self.clients), 2)

    def test_switching_from_repeat_to_once_respects_earlier_off(self):
        client = self.connect()
        client.reply({"state": "Active"})
        self.engine.configure(replace(self.engine.rule, repeat=False))
        self.advance()
        self.engine.tick()
        self.assertEqual(len(self.clients), 1)

    def test_pause_cancels_late_power_read(self):
        client = self.connect()
        callback = client.calls[-1][1]
        self.engine.configure(replace(self.rule, paused_on=self.clock.date().isoformat()))
        callback({"state": "Active"}, None)
        self.assertEqual(self.off_calls(), [])
        self.assertTrue(client.closed)

    def test_time_window_ending_cancels_late_power_read(self):
        client = self.connect()
        self.clock = datetime(2026, 10, 26, 0)
        client.reply({"state": "Active"})
        self.assertEqual(self.off_calls(), [])

    def test_disable_or_stop_cancels_late_connection(self):
        self.engine.tick()
        client = self.clients[-1]
        self.engine.stop()
        client.connected()
        self.assertEqual(client.calls, [])

    def test_reconfiguration_cancels_old_tv_callback(self):
        client = self.connect()
        callback = client.calls[-1][1]
        self.engine.configure(replace(self.rule, host=".".join(map(str, (10, 0, 0, 3)))))
        callback({"state": "Active"}, None)
        self.assertEqual(self.off_calls(), [])

    def test_power_read_failure_never_assumes_tv_is_on(self):
        client = self.connect()
        client.reply({}, "Permission denied")
        self.assertEqual(self.off_calls(), [])
        self.advance()
        self.engine.tick()
        self.assertEqual(len(client.calls), 2)

    def test_no_overlapping_reads_or_connections(self):
        self.engine.tick()
        self.engine.tick()
        self.assertEqual(len(self.clients), 1)
        self.clients[-1].connected()
        self.advance()
        self.engine.tick()
        self.assertEqual(len(self.clients[0].calls), 1)

    def test_hung_connection_is_closed_and_retried(self):
        self.engine.tick()
        first = self.clients[-1]
        self.advance(21)
        self.engine.tick()
        self.assertTrue(first.closed)
        self.advance()
        self.engine.tick()
        self.assertEqual(len(self.clients), 2)

    def test_pairing_failure_does_not_retry_until_reconfigured(self):
        self.engine.tick()
        client = self.clients[-1]
        client.background_blocked = True
        client.close()
        client.state("Pairing required")
        self.advance(60)
        self.engine.tick()
        self.assertEqual(len(self.clients), 1)
        self.engine.configure(self.rule)
        self.assertEqual(len(self.clients), 2)

    def test_persistence_error_prevents_dispatch(self):
        def broken(rule):
            raise OSError("Disk full")
        self.engine.persist = broken
        client = self.connect()
        client.reply({"state": "Active"})
        self.assertEqual(self.off_calls(), [])
        self.assertTrue(self.engine.blocked)

    def test_explicit_power_off_rejection_is_not_recorded_as_success(self):
        self.engine.configure(replace(self.rule, repeat=False))
        client = self.clients[-1]
        client.connected()
        client.reply({"state": "Active"})
        client.reply({}, "Permission denied")
        self.assertEqual(self.saved[-1].handled_window, "")
        self.assertTrue(self.engine.blocked)
        self.advance()
        self.engine.tick()
        self.assertIn("rejected", self.messages[-1])


class WarningTests(unittest.TestCase):
    make_engine = EngineTests.make_engine
    connect = EngineTests.connect
    advance = EngineTests.advance
    off_calls = EngineTests.off_calls

    def setUp(self):
        EngineTests.setUp(self)
        self.rule = replace(self.rule, warn_before_off=True)
        self.engine = self.make_engine(self.rule)

    def warn(self):
        client = self.connect()
        client.reply({"state": "Active"})
        self.assertEqual(client.calls[-1][0], "system.notifications/createToast")
        client.reply({"returnValue": True})
        return client

    def check_after(self, client, seconds):
        self.advance(seconds)
        self.engine.check_power()
        client.reply({"state": "Active"})

    def test_first_power_off_waits_full_minute(self):
        client = self.warn()
        self.check_after(client, 59)
        self.assertEqual(self.off_calls(), [])
        self.check_after(client, 1)
        self.assertEqual(len(self.off_calls()), 1)

    def test_warning_is_sent_one_minute_before_start(self):
        self.clock = datetime(2026, 10, 25, 20, 59)
        client = self.warn()
        self.assertEqual(self.off_calls(), [])
        self.check_after(client, 60)
        self.assertEqual(len(self.off_calls()), 1)

    def test_repeated_off_has_no_extra_warning_or_wait(self):
        client = self.warn()
        self.check_after(client, 60)
        client.reply({"returnValue": True})
        client.close()
        self.advance()
        self.engine.tick()
        second = self.clients[-1]
        second.connected()
        second.reply({"state": "Active"})
        self.assertEqual(second.calls[-1][0], "system/turnOff")
        self.assertEqual(len(self.off_calls()), 2)
        self.assertEqual(sum(call[0].endswith("createToast") for c in self.clients for call in c.calls), 1)

    def test_pause_during_countdown_cancels_off(self):
        client = self.warn()
        self.engine.configure(replace(self.engine.rule, paused_on=self.clock.date().isoformat(), warning_window="", warning_due=0))
        self.advance(60)
        self.engine.tick()
        self.assertEqual(self.off_calls(), [])
        self.assertTrue(client.closed)

    def test_notification_rejected_does_not_silently_power_off(self):
        client = self.connect()
        client.reply({"state": "Active"})
        client.reply({}, "Permission denied")
        self.advance(70)
        self.engine.tick()
        self.assertEqual(self.off_calls(), [])
        self.assertTrue(self.engine.blocked)

    def test_restart_preserves_warning_countdown_without_duplicate_toast(self):
        self.warn()
        saved = self.saved[-1]
        self.engine.stop()
        self.advance(30)
        self.engine = self.make_engine(saved)
        client = self.connect()
        client.reply({"state": "Active"})
        self.assertEqual(self.off_calls(), [])
        self.check_after(client, 30)
        self.assertEqual(len(self.off_calls()), 1)
        self.assertEqual(sum(call[0].endswith("createToast") for call in client.calls), 0)

    def test_clock_jump_does_not_shortcut_one_minute(self):
        client = self.warn()
        self.clock += timedelta(minutes=30)
        self.engine.check_power()
        client.reply({"state": "Active"})
        self.assertEqual(self.off_calls(), [])
        self.check_after(client, 60)
        self.assertEqual(len(self.off_calls()), 1)

    def test_no_warning_when_a_full_minute_would_extend_past_end(self):
        self.clock = datetime(2026, 10, 25, 23, 59, 30)
        client = self.connect()
        client.reply({"state": "Active"})
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(self.off_calls(), [])

    def test_late_active_response_after_midnight_does_not_power_off(self):
        self.clock = datetime(2026, 10, 25, 23, 58, 59)
        client = self.warn()
        self.advance(60)
        self.engine.check_power()
        self.clock = datetime(2026, 10, 26, 0)
        client.reply({"state": "Active"})
        self.assertEqual(self.off_calls(), [])


if __name__ == "__main__":
    unittest.main()
