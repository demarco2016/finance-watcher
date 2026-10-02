import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import finance_watcher as watcher


def coin(price=100, change=0):
    return {'id': 'bitcoin', 'symbol': 'btc', 'current_price': price, 'price_change_percentage_24h': change}


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.get.return_value.json.return_value = [coin()]

    def test_fetch_checks_status_and_sets_timeout(self):
        self.assertEqual(watcher.get_top10(self.session), [coin()])
        self.session.get.return_value.raise_for_status.assert_called_once()
        self.assertEqual(self.session.get.call_args.kwargs['timeout'], (5, 20))
        self.assertEqual(self.session.get.call_args.kwargs['params']['vs_currency'], 'usd')

    def test_http_and_connection_failures_are_explicit(self):
        for error in (requests.Timeout('private detail'), requests.HTTPError('429')):
            with self.subTest(error=type(error).__name__):
                self.session.get.side_effect = error
                with self.assertRaisesRegex(watcher.WatcherError, 'no fresh prices'):
                    watcher.get_top10(self.session)

    def test_http_status_is_not_treated_as_market_data(self):
        self.session.get.return_value.raise_for_status.side_effect = requests.HTTPError('429')
        with self.assertRaises(watcher.WatcherError):
            watcher.get_top10(self.session)
        self.session.get.return_value.json.assert_not_called()

    def test_malformed_json_is_explicit(self):
        self.session.get.return_value.json.side_effect = ValueError('bad JSON')
        with self.assertRaises(watcher.WatcherError):
            watcher.get_top10(self.session)

    def test_unusable_market_data_is_rejected(self):
        for data in ({'error': 'rate limited'}, [], [None], [coin(None)], [coin(-1)], [coin(float('nan'))], [coin(True)], [coin(change='bad')], [{**coin(), 'id': ''}]):
            with self.subTest(data=data):
                self.session.get.return_value.json.return_value = data
                with self.assertRaises(watcher.WatcherError):
                    watcher.get_top10(self.session)

    def test_missing_change_is_unavailable_and_zero_is_flat(self):
        report = watcher.build_report([coin(change=None), {**coin(change=0), 'id': 'other'}], {})
        self.assertIn('24h unavailable', report)
        self.assertIn('FLAT BTC', report)

    def test_threshold_boundaries_and_one_sided_limits(self):
        for price, limits, expected in ((90, {'low': 90, 'high': 110}, 'LOW'), (110, {'high': 110}, 'HIGH'), (100, {'low': 90, 'high': 110}, None)):
            with self.subTest(price=price):
                report = watcher.build_report([coin(price)], {'bitcoin': limits})
                if expected:
                    self.assertIn('hit ' + expected, report)
                else:
                    self.assertNotIn('ALERT', report)

    def test_coins_outside_top_ten_are_reported_unchecked(self):
        report = watcher.build_report([coin()], {'ethereum': {'low': 20}})
        self.assertIn('thresholds not checked: ethereum', report)


class ConfigTests(unittest.TestCase):
    def test_no_alert_file_means_no_active_thresholds(self):
        self.assertEqual(watcher.load_alerts(None), {})

    def test_valid_and_invalid_threshold_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'alerts.json'
            path.write_text(json.dumps({'bitcoin': {'low': 0}}))
            self.assertEqual(watcher.load_alerts(path), {'bitcoin': {'low': 0}})
            for data in ([], {'btc': {}}, {'btc': {'low': 10, 'high': 10}}, {'btc': {'low': -1}}, {'btc': {'low': True}}, {'btc': {'low': '1'}}, {'btc': {'high': float('inf')}}, {'btc': {'other': 1}}, {'btc': {'low': 10 ** 400}}):
                with self.subTest(data=data):
                    path.write_text(json.dumps(data))
                    with self.assertRaises(watcher.WatcherError):
                        watcher.load_alerts(path)
            path.write_text('not json')
            with self.assertRaises(watcher.WatcherError):
                watcher.load_alerts(path)

    def test_missing_alert_file(self):
        with self.assertRaises(watcher.WatcherError):
            watcher.load_alerts('/missing/path/alerts.json')

    def test_refresh_interval_is_finite_and_bounded(self):
        self.assertEqual(watcher.refresh_minutes('1.5'), 1.5)
        for value in ('0', '-1', 'nan', 'inf', '1441', 'bad'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                watcher.refresh_minutes(value)


class TelegramTests(unittest.TestCase):
    def test_success_is_checked(self):
        session = Mock()
        session.post.return_value.json.return_value = {'ok': True}
        watcher.send_telegram(session, 'report', 'dummy-token', 'dummy-chat')
        session.post.return_value.raise_for_status.assert_called_once()
        self.assertEqual(session.post.call_args.kwargs['timeout'], watcher.REQUEST_TIMEOUT)

    def test_api_failure_is_not_success(self):
        session = Mock()
        session.post.return_value.json.return_value = {'ok': False}
        with self.assertRaises(watcher.WatcherError):
            watcher.send_telegram(session, 'report', 'dummy-token', 'dummy-chat')

    def test_error_message_does_not_contain_token(self):
        session = Mock()
        session.post.side_effect = requests.Timeout('https://telegram/botdummy-secret')
        with self.assertRaises(watcher.WatcherError) as caught:
            watcher.send_telegram(session, 'report', 'dummy-secret', 'dummy-chat')
        self.assertNotIn('dummy-secret', str(caught.exception))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(watcher, 'load_dotenv'))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.stdout = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.session = self.stack.enter_context(patch.object(watcher.requests, 'Session')).return_value.__enter__.return_value
        self.session.get.return_value.json.return_value = [coin()]

    def test_once_succeeds_without_credentials_and_never_sends(self):
        self.assertEqual(watcher.main(['--once']), 0)
        self.session.post.assert_not_called()
        self.assertIn('FLAT BTC', self.stdout.getvalue())

    def test_configured_credentials_do_not_enable_delivery(self):
        os.environ.update(TELEGRAM_BOT_TOKEN='dummy-token', TELEGRAM_CHAT_ID='dummy-chat')
        self.assertEqual(watcher.main(['--once']), 0)
        self.session.post.assert_not_called()

    def test_failed_fetch_has_no_report_and_no_notification(self):
        os.environ.update(TELEGRAM_BOT_TOKEN='dummy-token', TELEGRAM_CHAT_ID='dummy-chat')
        self.session.get.side_effect = requests.Timeout()
        self.assertEqual(watcher.main(['--once', '--telegram']), 1)
        self.assertEqual(self.stdout.getvalue(), '')
        self.session.post.assert_not_called()
        self.assertIn('no fresh prices', self.stderr.getvalue())

    def test_telegram_missing_credentials_fails_before_fetch(self):
        self.assertEqual(watcher.main(['--once', '--telegram']), 1)
        self.session.get.assert_not_called()

    def test_delivery_failure_returns_nonzero_and_redacts_secret(self):
        os.environ.update(TELEGRAM_BOT_TOKEN='dummy-secret', TELEGRAM_CHAT_ID='dummy-chat')
        self.session.post.side_effect = requests.Timeout('botdummy-secret')
        self.assertEqual(watcher.main(['--once', '--telegram']), 1)
        self.assertNotIn('dummy-secret', self.stderr.getvalue())

    def test_continuous_mode_recovers_after_fetch_failure(self):
        self.session.get.side_effect = [requests.Timeout(), self.session.get.return_value]
        with patch.object(watcher.time, 'sleep', side_effect=[None, KeyboardInterrupt()]) as sleep:
            self.assertEqual(watcher.main(['--refresh-minutes', '2']), 0)
        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(sleep.call_args.args, (120,))
        self.assertIn('FLAT BTC', self.stdout.getvalue())

    def test_import_does_not_poll_or_run_forever(self):
        result = subprocess.run([sys.executable, '-c', 'import finance_watcher; print("imported")'], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'imported')


if __name__ == '__main__':
    unittest.main()
