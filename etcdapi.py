#!/usr/bin/env python3

# This file has been implemented with GLM-5.3-Flash on OpenCode

# etcdapi.py: a tiny etcd v3 client for the leader election.
#
# Standard library only, no external dependencies, just like the rest of
# the project. It speaks the etcd v3 JSON gateway (/v3/kv/range, /v3/kv/put,
# /v3/kv/txn, /v3/kv/deleterange and /v3/lease/grant) with urllib, so keys
# and values travel base64 encoded inside JSON.
#
# It is deliberately minimal: only what the leader election needs. Read and
# write single keys, an optional TTL through a lease, and the two
# compare-and-swap variants used to claim and renew the leadership.

import base64
import json
import urllib.request


class EtcdError(Exception):
    """ etcd did not answer what the API promises. """


def _encode(text):
    """ etcd v3 wants keys and values base64 encoded. """
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


def _decode(raw):
    return base64.b64decode(raw).decode('utf-8')


def _range_end(prefix):
    """ etcd ranges are [key, range_end): to select every key under a
    " prefix, range_end is the prefix with its last byte incremented.
    """

    raw = bytearray(prefix.encode('utf-8'))
    for index in range(len(raw) - 1, -1, -1):
        if raw[index] < 0xff:
            raw[index] += 1
            return bytes(raw[:index + 1]).decode('utf-8')
    raise EtcdError(f"no range_end possible for {prefix!r}")


class Etcd:
    """ A very small etcd v3 client (JSON gateway only). """

    def __init__(self, host='localhost', port=2379, timeout=2.0):
        self.url = f"http://{host}:{port}"
        self.timeout = timeout

    def _post(self, path, payload):
        """ POST a JSON payload and return the decoded JSON answer. """

        http_request = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'})

        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as reply:
                return json.loads(reply.read().decode('utf-8'))
        except (OSError, ValueError) as exc:
            raise EtcdError(f"{path}: {exc}")

    def _grant(self, ttl):
        """ Grant a lease that expires after ttl seconds. """
        return self._post('/v3/lease/grant', {'TTL': str(int(ttl))})['ID']

    # -- plain operations ---------------------------------------------------

    def get(self, key):
        """ The value of a key, or None when it does not exist. """

        answer = self._post('/v3/kv/range', {'key': _encode(key)})
        kvs = answer.get('kvs') or []
        return _decode(kvs[0]['value']) if kvs else None

    def prefix(self, prefix):
        """ Every key/value pair under a prefix, as a dict.

        " This is how the workforce is read: one range for the whole
        " strike/workforce/ prefix.
        """

        answer = self._post('/v3/kv/range', {
            'key': _encode(prefix),
            'range_end': _encode(_range_end(prefix)),
        })
        return {_decode(kv['key']): _decode(kv['value'])
                for kv in answer.get('kvs') or []}

    def put(self, key, value, ttl=None):
        """ Put a key, attached to a fresh lease when a TTL is given. """

        payload = {'key': _encode(key), 'value': _encode(value)}
        if ttl:
            payload['lease'] = self._grant(ttl)

        self._post('/v3/kv/put', payload)

    def delete(self, key):
        self._post('/v3/kv/deleterange', {'key': _encode(key)})

    # -- compare-and-swap ---------------------------------------------------

    def _txn(self, compare, success):
        """ Run a transaction, telling whether the comparison succeeded. """

        answer = self._post('/v3/kv/txn', {
            'compare': compare,
            'success': success,
            'failure': [],
        })
        return bool(answer.get('succeeded'))

    def put_if_absent(self, key, value, ttl=None):
        """ Put the key only when it does not exist yet.

        " This is how a node claims the leadership.
        """

        request_put = {'key': _encode(key), 'value': _encode(value)}
        if ttl:
            request_put['lease'] = self._grant(ttl)

        compare = [{'key': _encode(key), 'target': 'VERSION',
                    'operator': 'EQUAL', 'version': '0'}]

        return self._txn(compare, [{'request_put': request_put}])

    def put_if_value(self, key, expected, value, ttl=None):
        """ Put the key only when it holds the expected value.

        " This is how the leader renews its lease, and how it notices
        " that it lost the key to somebody else.
        """

        request_put = {'key': _encode(key), 'value': _encode(value)}
        if ttl:
            request_put['lease'] = self._grant(ttl)

        compare = [{'key': _encode(key), 'target': 'VALUE',
                    'operator': 'EQUAL', 'value': _encode(expected)}]

        return self._txn(compare, [{'request_put': request_put}])

    def delete_if_value(self, key, expected):
        """ Delete the key only when it holds the expected value.

        " This is how a leader steps down.
        """

        compare = [{'key': _encode(key), 'target': 'VALUE',
                    'operator': 'EQUAL', 'value': _encode(expected)}]

        return self._txn(compare, [{'request_delete_range': {'key': _encode(key)}}])
