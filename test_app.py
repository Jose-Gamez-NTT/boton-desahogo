import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

import app


class ActivityTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual([app.state_for(number) for number in range(8)], [
            'calm', 'uneasy', 'uneasy', 'hot', 'hot', 'hot', 'fire', 'fire',
        ])

    def test_one_decay_per_hour_and_exact_boundary(self):
        self.assertEqual(app.calculate_activity([0, 5, 10], 3599), (3, 3600))
        self.assertEqual(app.calculate_activity([0, 5, 10], 3600), (2, 7200))
        self.assertEqual(app.calculate_activity([0, 5, 10], 7200), (1, 10800))
        self.assertEqual(app.calculate_activity([0, 5, 10], 10800), (0, None))

    def test_new_activity_does_not_reset_running_clock(self):
        self.assertEqual(app.calculate_activity([0, 3500, 3700], 3700), (2, 7200))

    def test_clock_restarts_when_activity_reaches_zero(self):
        self.assertEqual(app.calculate_activity([0, 4000], 4000), (1, 7600))
        self.assertEqual(app.calculate_activity([0, 3600], 3600), (1, 7200))

    def test_future_entries_are_not_active(self):
        self.assertEqual(app.calculate_activity([100, 200], 150), (1, 3700))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'test.sqlite3'
        app.initialize(self.database)
        app.initialize(self.database)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(self.database))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f'127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        status = response.status
        connection.close()
        return status, data

    def post(self, data, origin=True):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = f'http://{self.host}'
        return self.request('POST', '/api/venting', json.dumps(data).encode('utf-8'), headers)

    def test_pages_and_initial_state(self):
        for path in ('/', '/app.js', '/styles.css'):
            self.assertEqual(self.request('GET', path)[0], 200)
        status, body = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        applications = json.loads(body)['applications']
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0]['name'], 'aXet.code')
        self.assertEqual(applications[0]['state'], 'calm')

    def test_submit_and_persist_history(self):
        status, body = self.post({'application_id': 1, 'message': '  No funciona 😤  '})
        self.assertEqual(status, 201)
        application = json.loads(body)['applications'][0]
        self.assertEqual(application['active'], 1)
        self.assertEqual(application['state'], 'uneasy')
        self.assertEqual(application['history'][0]['message'], 'No funciona 😤')
        self.assertEqual(app.snapshot(self.database)['applications'][0]['history'][0]['message'], 'No funciona 😤')
        self.assertEqual(app.snapshot(self.database, now=4102444800)['applications'][0]['active'], 0)
        self.assertEqual(len(app.snapshot(self.database, now=4102444800)['applications'][0]['history']), 1)

    def test_validation_and_origin(self):
        for data in ({'application_id': 1, 'message': '   '}, {'application_id': 1, 'message': 'x' * 2001}, {'application_id': True, 'message': 'hola'}, []):
            self.assertEqual(self.post(data)[0], 400)
        self.assertEqual(self.post({'application_id': 99, 'message': 'hola'})[0], 404)
        self.assertEqual(self.post({'application_id': 1, 'message': 'hola'}, origin=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Host': 'attacker.example'})[0], 400)
        self.assertEqual(self.request('GET', '/app.py')[0], 404)
        self.assertEqual(app.snapshot(self.database)['applications'][0]['history'], [])


if __name__ == '__main__':
    unittest.main()
