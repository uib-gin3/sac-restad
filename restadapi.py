#!/usr/bin/env python3

# This file has been fully vibe-coded with MiniMax-M3.1-Flash on OpenCode

# restadapi.py: a tiny REST client for the restad calculator API.
#
# Standard library only, no external dependencies, just like the rest of the
# project. It speaks HTTP/1.1 on top of http.client and keeps the connection
# alive when the server allows it.
#
# The gunicorn sync worker forces the connection closed after every response
# (see the comment in gunicorn/workers/sync.py) so, in practice, a new TCP
# connection is opened for every request. The client does not care: it
# reconnects transparently and keeps count of the connections opened and of
# the bytes exchanged.

import http.client
import sys

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 12345

# The operations understood by the server
OPERATIONS = ('add', 'sub', 'div', 'mult', 'sqrt', 'mean', 'std', 'reset')


class RestadError(Exception):
    """ The server did not answer what the API promises. """


class Response:
    """ A minimal response: status code, headers and body. """

    def __init__(self, status, reason, headers, body, will_close=False):
        self.status = status
        self.reason = reason
        self.headers = headers          # dict, keys in lower case
        self.body = body                # bytes
        self.text = body.decode('utf-8', errors='replace')
        self.will_close = will_close

    @property
    def ok(self):
        return 200 <= self.status < 300

    def header(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def __str__(self):
        return f"{self.status} {self.reason}"


class Restad:
    """ A very small REST client for the restad API. """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=10.0,
                 verbose=False):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.verbose = verbose
        self.conn = None
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.connections = 0

    # -- connection handling ------------------------------------------------

    def _connect(self):

        if self.conn is None:
            self.conn = http.client.HTTPConnection(self.host, self.port,
                                                   timeout=self.timeout)
            self.connections += 1

        return self.conn

    def close(self):

        if self.conn is not None:
            try:
                self.conn.close()
            except OSError:
                pass
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # -- the request --------------------------------------------------------

    def request(self, method, path, body=None, headers=None):
        """ Send a request and return the Response.

        " Raises OSError or http.client.HTTPException if the connection
        " fails, the caller is responsible to retry if it wants to.
        """

        if isinstance(body, str):
            payload = body.encode('utf-8')
        elif body is None:
            payload = b''
        else:
            payload = body

        hdrs = dict(headers or {})
        if payload:
            hdrs.setdefault('Content-Type', 'text/plain; charset=utf-8')
            hdrs['Content-Length'] = str(len(payload))

        conn = self._connect()

        if self.verbose:
            print(f"> {method} {path} HTTP/1.1", file=sys.stderr)
            for name, value in hdrs.items():
                print(f"> {name}: {value}", file=sys.stderr)
            if payload:
                print(f"> {payload.decode('utf-8', 'replace')}", file=sys.stderr)
            print(">", file=sys.stderr)

        # putrequest/putheader are used instead of the shortcut request()
        # to know exactly what goes on the wire: the byte counters of the
        # benchmark have to be honest.
        conn.putrequest(method, path, skip_accept_encoding=True)
        for name, value in hdrs.items():
            conn.putheader(name, value)
        conn.endheaders(payload)

        raw = conn.getresponse()
        data = raw.read()
        received = raw.getheaders()

        if self.verbose:
            print(f"< HTTP/1.1 {raw.status} {raw.reason}", file=sys.stderr)
            for name, value in received:
                print(f"< {name}: {value}", file=sys.stderr)
            if data:
                print(f"< {data.decode('utf-8', 'replace')}", file=sys.stderr)
            print("<", file=sys.stderr)

        self.bytes_sent += self._request_size(method, path, hdrs, payload)
        self.bytes_recv += self._response_size(raw, received, data)

        response = Response(raw.status, raw.reason,
                            {name.lower(): value for name, value in received},
                            data, raw.will_close)

        if raw.will_close:
            # The server does not want to keep the connection alive
            self.close()

        return response

    def _request_size(self, method, path, headers, payload):
        """ Bytes written on the wire for a request (headers included). """

        size = len(f"{method} {path} HTTP/1.1\r\n")
        size += len(f"Host: {self.host}:{self.port}\r\n")

        for name, value in headers.items():
            size += len(f"{name}: {value}\r\n")

        # The empty line closing the headers
        size += 2

        return size + len(payload)

    def _response_size(self, raw, headers, body):
        """ Bytes read from the wire for a response (headers included). """

        size = len(f"HTTP/1.1 {raw.status} {raw.reason}\r\n")

        for name, value in headers:
            size += len(f"{name}: {value}\r\n")

        return size + 2 + len(body)

    # -- the restad API -----------------------------------------------------

    def create(self, operands, calc_id=None):
        """ Create a new calculus with the given operands.

        " POST /calc when the id is chosen by the server, PUT /calc/<id>
        " when the user chooses it.
        " Returns a (calc_id, response) tuple.
        """

        body = ','.join(str(x) for x in operands)

        if calc_id is None:
            response = self.request('POST', '/calc', body)
            if response.status != 201:
                raise RestadError(f"cannot create the calculus: "
                                  f"{response.status} {response.text}")
            return response.text.strip(), response

        response = self.request('PUT', f'/calc/{calc_id}', body)
        if response.status != 201:
            raise RestadError(f"cannot create the calculus: "
                              f"{response.status} {response.text}")

        return calc_id, response

    def get(self, calc_id):
        """ GET /calc/<id>: the list of operands. """

        return self.request('GET', f'/calc/{calc_id}')

    def patch(self, calc_id, operands):
        """ PATCH /calc/<id>: add operands to an existing calculus. """

        body = ','.join(str(x) for x in operands)

        return self.request('PATCH', f'/calc/{calc_id}', body)

    def apply(self, calc_id, operation, store=False):
        """ Apply an operation to a calculus.

        " With store=True (POST) the result is kept as the new value of
        " the calculus, with store=False (GET) the calculus is not touched.
        """

        method = 'POST' if store else 'GET'

        return self.request(method, f'/calc/{calc_id}/{operation}')

    def delete(self, calc_id):
        """ DELETE /calc/<id>: forget the calculus. """

        return self.request('DELETE', f'/calc/{calc_id}')
