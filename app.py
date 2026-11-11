#!/usr/bin/env python3

# Except for djb2_hex, the regex and acquire_lock (AI generated), all the code
# in this file has been implemented old school way by hand, just using AI tools
# as a search assistant.
#
# The strike mode section (etcd leader election, delegation to colleagues,
# strikes and burnouts) has been implemented with GLM-5.3-Flash on OpenCode
# for the sac-strike assignment.

import re
import os
import sys
import time
import json
import random
import operator
import socket
import threading
import functools
import http.client

from math import sqrt
from urllib.parse import urlsplit
from functools import reduce
from statistics import mean, stdev, quantiles, StatisticsError

from bottle import Bottle, response, request, run


######################### Setup mem system ###################################

class LockTimeout(Exception):
    pass

USE_REDIS = '--redis' in sys.argv or os.environ.get('USE_REDIS') == '1'

if USE_REDIS:
    import redis
    mem = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

    class acquire_lock:
        def __init__(self):
            self.lock = mem.lock('restad', timeout=5, blocking_timeout=2.0)
            
        def __enter__(self):
            try:
                self.lock.__enter__()
            except redis.exceptions.LockError:
                raise LockTimeout()
                
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.lock.__exit__(exc_type, exc_val, exc_tb)

else:
    import multiprocessing

    manager = multiprocessing.Manager()
    mem = manager.dict()
    lock = manager.Lock()

    class acquire_lock:
        def __enter__(self):
            if not lock.acquire(timeout=2.0):
                raise LockTimeout()
                
        def __exit__(self, exc_type, exc_val, exc_tb):
            lock.release()


def store_session(session, value):
    """
    " Stores the session value
    " If USE_REDIS is false it is assumed that a single process is doing
    " the work so just a shared dict is fine.
    " If USE_REDIS is true we use an external shared memory across
    " all processes.
    """

    if USE_REDIS:
        mem.set(session, json.dumps(value))
    else:
        mem[session] = value


def get_session(session):

    if USE_REDIS:
        data = mem.get(session)
        if data is None:
            raise KeyError(session)
        return json.loads(data)
    else:
        return mem[session]


def delete_session(session):

    if USE_REDIS:
        mem.delete(session)
    else:
        mem.pop(session)

    
######################### Some aux functions ###################################

def djb2_hex(text):
    """ Simple hash function given a text returns the hex hash.
    " Daniel J. Bernstein is just awesome, just a tribute <3
    " http://www.cse.yorku.ca/~oz/hash.html
    """

    hash_val = 5381

    for byte in text.encode('utf-8'):
        hash_val = ((hash_val << 5) + hash_val) + byte
        hash_val &= 0xFFFFFFFF

    return f"{hash_val:08x}"


def generate_id():
    """
    " Given a request returns a session_id
    " Hashing some connection elements + random to avoid collisions.
    """
    timestamp = str(time.time())
    client_ip = request.environ.get('REMOTE_ADDR', '')
    client_port = request.environ.get('REMOTE_PORT', '')
    rnd = random.random()

    return djb2_hex(f"{timestamp}:{client_ip}:{client_port}:{rnd}")


def parse_operands():
    """
    " Extract and parse the operands from the request body
    " @return a dict with:
    "   data -> with the list of operands (if no error)
    "   status -> with the status code to be given if error
    "   error -> with the error message
    """
    parsed = {}

    try:
        raw_data = request.body.read().decode('utf-8')
    except UnicodeDecodeError as exc:
        parsed['status'] = 400
        parsed['error'] = str(exc)
        return parsed

    # Thanks AI for writing such a good regex :D (hope it has no bugs)
    pattern = r'^[-+]?(?:\d+\.?\d*|\.\d+)(?:,[-+]?(?:\d+\.?\d*|\.\d+))*$'
    if not re.match(pattern, raw_data):
        parsed['status'] = 400
        parsed['error'] = "Invalid number(s)"
        return parsed

    return {
        'data': [float(n) if '.' in n else int(n) for n in raw_data.split(',')]
    }

######################### Strike mode #########################################
#
# The calculators' strike: a leader elected through etcd, delegation to
# colleagues, strikes and burnouts. All of it is switched on by the
# STRIKE_ environment variables, without them the calculator below
# behaves exactly as it always did.

HOSTNAME = socket.gethostname()

STRIKE_ETCD = os.environ.get('STRIKE_ETCD', '')               # host[:port]
STRIKE_COLLEAGUES = os.environ.get('STRIKE_COLLEAGUES', '')   # http endpoints
DISTRIBUTED = bool(STRIKE_ETCD) and bool(STRIKE_COLLEAGUES)

STRIKE_ALGORITHM = os.environ.get('STRIKE_ALGORITHM', 'random').lower()
STRIKE_LEADING_OVERHEAD = float(os.environ.get('STRIKE_LEADING_OVERHEAD', 0.1))
STRIKE_MIN_TIME = float(os.environ.get('STRIKE_MIN_TIME', 2.0))
STRIKE_MAX_TIME = float(os.environ.get('STRIKE_MAX_TIME', 6.0))
STRIKE_BURNOUT_MIN_TIME = float(os.environ.get('STRIKE_BURNOUT_MIN_TIME', 8.0))
STRIKE_BURNOUT_MAX_TIME = float(os.environ.get('STRIKE_BURNOUT_MAX_TIME', 20.0))
STRIKE_RETRY = int(os.environ.get('STRIKE_RETRY', 5))
STRIKE_LEADER_TTL = int(os.environ.get('STRIKE_LEADER_TTL', 4))
STRIKE_TIMEOUT = float(os.environ.get('STRIKE_TIMEOUT', 5.0))

COLLEAGUES = [c.strip().rstrip('/') for c in STRIKE_COLLEAGUES.split(',')
              if c.strip()]
# Every node gets the same list (itself included) and excludes itself
# when delegating, matching endpoints by hostname.
SELF = next((c for c in COLLEAGUES if urlsplit(c).hostname == HOSTNAME), None)
PEERS = [c for c in COLLEAGUES if c != SELF]

LEADER_KEY = 'strike/leader'
LEADER_TICK = 0.5      # seconds between two campaign ticks

# All the strike state lives in the process memory: only the deadlines
# matter (time.time() based) and everything else is derived from them.
STATE = {
    'strike_until': 0.0,    # answering 418 to the calculations
    'burnout_at': 0.0,      # deadline of the auto-destruction countdown
    'burnout_until': 0.0,   # 418 window after the countdown fires
    'leader': None,         # leader hostname as seen in etcd
    'am_leader': False,
    'unhealthy': False,     # to notice and log the recoveries
}
LOCK = threading.Lock()

if DISTRIBUTED:
    from etcdapi import Etcd, EtcdError


def on_strike():
    with LOCK:
        return time.time() < STATE['strike_until']


def burned_out():
    with LOCK:
        return time.time() < STATE['burnout_until']


def am_leader():
    with LOCK:
        return STATE['am_leader']


def self_probability():
    """ Probability of the leader doing the operation itself.

    " 1/N - (1/N * STRIKE_LEADING_OVERHEAD), N being the number of
    " instances of the fleet. With 5 instances and an overhead of 0.1:
    " 1/5 - (1/5 * 0.1) = 0.18
    """

    if not COLLEAGUES:
        return 1.0

    share = 1.0 / len(COLLEAGUES)
    return max(0.0, share - share * STRIKE_LEADING_OVERHEAD)


def node_key(endpoint):
    """ Redis keys and narration speak of nodes by hostname. """
    return urlsplit(endpoint).hostname or endpoint


def endpoint_parts(endpoint):
    """ (host, port) of an http://host:port colleague endpoint. """
    parts = urlsplit(endpoint)
    return parts.hostname or '127.0.0.1', parts.port or 12345


def _safe_redis(action):
    """ Redis hiccups must never take a calculation down. """
    if not USE_REDIS:
        return None
    try:
        return action()
    except redis.exceptions.RedisError:
        return None


def mem_incr(key):
    return _safe_redis(lambda: mem.incr(key))


def record_node(node, elapsed, ok):
    """ The leader keeps track of who responded, how long it took and
    " whether the operation failed. These counters in Redis are also
    " what the robust and fastest delegation algorithms read.
    """

    if not USE_REDIS:
        return

    def update():
        if ok:
            mem.incr(f"strike:ok:{node}")
            mem.incrbyfloat(f"strike:time:{node}", elapsed)
        else:
            mem.incr(f"strike:fail:{node}")

    _safe_redis(update)


def log_event(kind, detail=''):
    """ Append an event to the shared log, the strike-demo summary is
    " built from here: elections, step downs, strikes, burnouts...
    """

    if not USE_REDIS:
        return

    entry = json.dumps({'t': round(time.time(), 3), 'node': HOSTNAME,
                        'kind': kind, 'detail': str(detail)})

    def update():
        mem.lpush('strike:events', entry)
        mem.ltrim('strike:events', 0, 3999)

    _safe_redis(update)


def choose_backend(exclude):
    """ Pick the next colleague to delegate to.

    " robust  -> the one with the fewest failures
    " fastest -> the one with the lowest average response time
    " random  -> anybody
    " Ties are broken randomly.
    """

    peers = [peer for peer in PEERS if peer not in exclude]
    if not peers:
        return None

    if STRIKE_ALGORITHM == 'random' or not USE_REDIS:
        return random.choice(peers)

    scored = []
    for endpoint in peers:
        node = node_key(endpoint)
        ok = int(_safe_redis(lambda node=node: mem.get(f"strike:ok:{node}")) or 0)
        fail = int(_safe_redis(lambda node=node: mem.get(f"strike:fail:{node}")) or 0)
        total = float(_safe_redis(lambda node=node: mem.get(f"strike:time:{node}")) or 0)
        scored.append((endpoint, fail, total / ok if ok else 0.0))

    random.shuffle(scored)
    if STRIKE_ALGORITHM == 'robust':
        return min(scored, key=lambda score: (score[1], score[2]))[0]
    if STRIKE_ALGORITHM == 'fastest':
        return min(scored, key=lambda score: (score[2], score[1]))[0]

    return random.choice(peers)


def delegate():
    """ Forward the request to a colleague and relay its answer.

    " The colleague is picked with the current algorithm, its answer is
    " relayed together with its X-Served-By header, and how it went is
    " recorded in Redis. On failure the leader retries with a different
    " colleague, up to STRIKE_RETRY times.
    """

    method = request.method
    path = request.environ.get('PATH_INFO', '/')
    if request.environ.get('QUERY_STRING'):
        path = f"{path}?{request.environ['QUERY_STRING']}"

    body = request.body.read()
    headers = {'X-Delegated-By': HOSTNAME}
    if body:
        headers['Content-Type'] = 'text/plain; charset=utf-8'
        headers['Content-Length'] = str(len(body))

    tried = set()
    for _ in range(max(1, STRIKE_RETRY)):
        endpoint = choose_backend(tried)
        if endpoint is None:
            break
        tried.add(endpoint)
        host, port = endpoint_parts(endpoint)

        started = time.monotonic()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=STRIKE_TIMEOUT)
            conn.request(method, path, body=body or None, headers=headers)
            raw = conn.getresponse()
            data = raw.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            record_node(node_key(endpoint), time.monotonic() - started, ok=False)
            log_event('delegated_failed', f"{node_key(endpoint)}: {exc}")
            continue

        elapsed = time.monotonic() - started
        if raw.status == 418 or raw.status >= 500:
            record_node(node_key(endpoint), elapsed, ok=False)
            log_event('delegated_failed', f"{node_key(endpoint)}: {raw.status}")
            continue

        record_node(node_key(endpoint), elapsed, ok=True)
        mem_incr('strike:delegated')

        response.status = raw.status
        response.set_header('X-Served-By',
                            raw.getheader('X-Served-By') or node_key(endpoint))
        response.set_header('X-Leaded-By', HOSTNAME)

        # The API promises a Location header on creates; the colleague
        # wrote it with its own host, rewrite it with ours.
        location = raw.getheader('Location')
        if location:
            scheme, host = request.urlparts[0], request.urlparts[1]
            response.set_header('Location', f"{scheme}://{host}"
                                            f"{urlsplit(location).path}")

        return data.decode('utf-8', errors='replace')

    log_event('orphans', f"tried {', '.join(sorted(tried)) or 'nobody'}")
    response.status = 503
    return "Error: nobody could serve the request, all colleagues are on strike"


def status_code():
    """ response.status is an int or a string depending on the Bottle
    " version, this always gives the number.
    """
    code = response.status
    return code if isinstance(code, int) else int(str(code).split()[0])


def distributed(func):
    """ Decide per request: do the operation here or delegate it.

    " Struck or burned out nodes answer 418 I'm a teapot to every
    " calculation. Non-leader nodes always do the operation themselves.
    " The leader does it itself with probability
    " 1/N - (1/N * STRIKE_LEADING_OVERHEAD) and delegates the rest,
    " except when the request arrives already delegated (that would be
    " a ping-pong between two nodes that both believe they lead).
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        now = time.time()
        with LOCK:
            strike_until = STATE['strike_until']
            burnout_until = STATE['burnout_until']

        if now < strike_until:
            response.status = 418
            return f"I'm a teapot: on strike for {strike_until - now:.1f}s more"

        if now < burnout_until:
            response.status = 418
            return f"I'm a teapot: burned out for {burnout_until - now:.1f}s more"

        if not DISTRIBUTED:
            return func(*args, **kwargs)

        if (am_leader()
                and request.get_header('X-Delegated-By') is None
                and random.random() >= self_probability()):
            return delegate()

        if am_leader() and request.get_header('X-Delegated-By') is None:
            mem_incr('strike:self')
            started = time.monotonic()
            try:
                result = func(*args, **kwargs)
            except Exception:
                record_node(HOSTNAME, time.monotonic() - started, ok=False)
                raise
            code = status_code()
            record_node(HOSTNAME, time.monotonic() - started,
                        ok=code != 418 and code < 500)
            return result

        return func(*args, **kwargs)

    return wrapper


def tick(etcd):
    """ One campaign tick: elect, renew or step down.

    " The whole election is a single etcd key with a lease. A healthy
    " node claims it when it is free (put_if_absent) and renews it
    " while it leads (put_if_value with a fresh lease). A struck or
    " burned out leader deletes the key and steps down, and when a
    " leader just dies the lease expires and the key goes away: the
    " next tick somebody else claims it.
    """

    now = time.time()
    with LOCK:
        strike = now < STATE['strike_until']
        burnt = now < STATE['burnout_until']
        burnout_due = STATE['am_leader'] and now >= STATE['burnout_at']
        was_unhealthy = STATE['unhealthy']
        STATE['unhealthy'] = strike or burnt
    healthy = not (strike or burnt)

    if was_unhealthy and healthy:
        log_event('recovered')

    if STATE['am_leader']:
        if strike:
            etcd.delete_if_value(LEADER_KEY, HOSTNAME)
            log_event('stepped_down', 'on strike')
            with LOCK:
                STATE['am_leader'] = False
                STATE['leader'] = None
        elif burnout_due:
            with LOCK:
                STATE['burnout_until'] = now + random.uniform(STRIKE_MIN_TIME,
                                                              STRIKE_MAX_TIME)
            etcd.delete_if_value(LEADER_KEY, HOSTNAME)
            log_event('burned_out', f"{STATE['burnout_until'] - now:.1f}s of teapot")
            with LOCK:
                STATE['am_leader'] = False
                STATE['leader'] = None
        elif not etcd.put_if_value(LEADER_KEY, HOSTNAME, HOSTNAME,
                                   ttl=STRIKE_LEADER_TTL):
            log_event('stepped_down', 'lost the leadership key')
            with LOCK:
                STATE['am_leader'] = False
                STATE['leader'] = None
        return

    # Follower: claim the key when it is free and we are healthy.
    if healthy and etcd.get(LEADER_KEY) is None:
        if etcd.put_if_absent(LEADER_KEY, HOSTNAME, ttl=STRIKE_LEADER_TTL):
            burnout_in = random.uniform(STRIKE_BURNOUT_MIN_TIME,
                                        STRIKE_BURNOUT_MAX_TIME)
            with LOCK:
                STATE['am_leader'] = True
                STATE['burnout_at'] = now + burnout_in
                STATE['leader'] = HOSTNAME
            log_event('elected', f"burnout in {burnout_in:.1f}s")
            return

    with LOCK:
        STATE['leader'] = etcd.get(LEADER_KEY)


def campaign():
    """ Background thread that keeps the leadership state fresh. """

    host, _, port = STRIKE_ETCD.partition(':')
    etcd = Etcd(host, int(port or 2379))

    while True:
        try:
            tick(etcd)
        except (EtcdError, OSError):
            pass  # etcd unreachable: keep whatever we knew
        time.sleep(LEADER_TICK)


if DISTRIBUTED:
    threading.Thread(target=campaign, name='campaign', daemon=True).start()


######################### The app itself ###################################

app = Bottle()


# Operations are not important, we want to focus on the
# API side so: let's be compact and hacky, which is fun yet not convenient
# on real projects.
operations = {
    "add": lambda operands: reduce(operator.add, operands),
    "sub": lambda operands: reduce(operator.sub, operands),
    "div": lambda operands: reduce(operator.truediv, operands),
    "mult": lambda operands: reduce(operator.mul, operands),
                                                                     # Force the error
    "sqrt": lambda operands: sqrt(operands[0]) if len(operands) == 1 else sqrt(operands),
    "mean": lambda operands: mean(operands),
    "std": lambda operands: stdev(operands),
}


@app.hook('before_request')
def set_default_headers():
    """
    " Set common things to all requests
    """
    response.content_type = 'text/plain; charset=utf-8'
    request.environ['REQUEST_START_TIME'] = time.time()


@app.hook('after_request')
def set_final_headers():
    """
    " Set common things to all requests
    """
    start_time = request.environ.get('REQUEST_START_TIME')
    if start_time:
        elapsed_time = time.time() - start_time
        response.set_header('X-Response-Time', f"{elapsed_time:.4f}s")

    # The node that computed the operation signs it. When the leader
    # delegated, it already relayed the colleague's signature.
    if not response.get_header('X-Served-By'):
        response.set_header('X-Served-By', HOSTNAME)

    # The leader signs as the one leading, unless the answer already
    # carries it (delegated answers are signed in the relay).
    if DISTRIBUTED and am_leader() and not response.get_header('X-Leaded-By'):
        response.set_header('X-Leaded-By', HOSTNAME)


# POST creates and generates id
@app.post("/calc")
# PUT is idempotent user chooses id
@app.put("/calc/<calc_id>")
@distributed
def create(calc_id=None):
    """
    " Create a new calculus adding the payload of comma separated numbers
    " (if given). Will return the calc-id to use in further requests.
    "
    "   /calc
    "   body: 1,2
    "
    "   201 Created
    "   3db3123f21314
    """

    parsed = parse_operands()
    if 'error' in parsed:
        response.status = parsed['status']
        return parsed['error']

    if not calc_id:
        calc_id = generate_id()

    store_session(calc_id, parsed['data'])

    response.status = 201
    scheme, host = request.urlparts[0], request.urlparts[1]
    response.set_header('Location', f'{scheme}://{host}/calc/{calc_id}')

    return str(calc_id)


@app.patch("/calc/<calc_id>")
@distributed
def update(calc_id):
    """
    " Add operands to an existing calculus as a list of comma separated numbers.
    " Will return the current number of operands.
    "
    "   /calc/<calc_id>
    "   body: 3,4
    "
    "   200 OK
    "   4
    """

    parsed = parse_operands()
    if 'error' in parsed:
        response.status = parsed['status']
        return parsed['error']


    with acquire_lock():
        try:
            operands = get_session(calc_id)
        except KeyError:
            response.status = 404
            return f'Error: calc {calc_id} does not exist'

        operands.extend(parsed['data'])
        store_session(calc_id, operands)

    response.status = 200
    return str(len(operands))


@app.get("/calc/<calc_id>")
@distributed
def get(calc_id):

    try:
        data = get_session(calc_id)
    except KeyError:
        response.status = 404
        return f'Error: calc {calc_id} does not exist'

    return ",".join([str(x) for x in data]) 


@app.route("/calc/<calc_id>/<operation>", method=['GET', 'POST'])
@distributed
def calculate(calc_id, operation):
    """
    " Returns the desired operation applied to the stored operand list
    " GET does not modify the list POST does.
    "   /calc/31f6266f/add
    "
    "   200 OK
    "   3
    """

    try:
        operands = get_session(calc_id)
    except KeyError:
        response.status = 404
        return f'Error: calc {calc_id} does not exist'

    if operation == 'reset':
        store_session(calc_id, [])
        response.status = 200
        return 'resetted'

    if operation not in operations.keys():
        response.status = 409
        return "Error: not a valid operation"

    try:
        result = operations[operation](operands)
    except (ArithmeticError, StatisticsError, TypeError, ValueError) as exc:
        response.status = 422
        return f"Error: {exc}"

    if request.method == 'POST':
        store_session(calc_id, [result])

    response.status = 200

    return str(result)


@app.route("/strike", method=['GET', 'POST'])
def strike():
    """
    " Go on strike for a random time between STRIKE_MIN_TIME and
    " STRIKE_MAX_TIME seconds. While on strike the node answers
    " 418 I'm a teapot to every calculation, and a leader steps down
    " immediately.
    "
    "   POST localhost:12345/strike
    "
    "   200 OK
    "   on strike for 4.2s
    """

    now = time.time()
    with LOCK:
        if now < STATE['strike_until']:
            response.status = 200
            return f"already on strike for {STATE['strike_until'] - now:.1f}s more"

        duration = random.uniform(STRIKE_MIN_TIME, STRIKE_MAX_TIME)
        STATE['strike_until'] = now + duration

    log_event('on_strike', f"{duration:.1f}s")
    response.status = 200
    return f"on strike for {duration:.1f}s"


@app.get("/health")
def health():
    """
    " Health of the node: 200 when it can serve, 418 (with the reason)
    " when it is on strike or burned out. It always answers, even when
    " on strike, so whoever watches can see the recovery.
    "
    "   GET localhost:12345/health
    "
    "   200 OK
    "   healthy, leader: node3
    """

    now = time.time()
    with LOCK:
        strike_left = STATE['strike_until'] - now
        burnout_left = STATE['burnout_at'] - now
        burnt_left = STATE['burnout_until'] - now
        leader = STATE['leader']

    if strike_left > 0:
        response.status = 418
        return f"on strike for {strike_left:.1f}s"

    if burnt_left > 0:
        response.status = 418
        return f"burned out for {burnt_left:.1f}s"

    if am_leader():
        if burnout_left > 0:
            return f"leading, burnout in {burnout_left:.1f}s"
        return "leading"

    return f"healthy, leader: {leader or 'none'}"


@app.delete("/calc/<calc_id>")
@distributed
def delete(calc_id):

    try:
        data = get_session(calc_id)
    except KeyError:
        response.status = 404
        return f'Error: calc {calc_id} does not exist'
    
    delete_session(calc_id)

    response.status = 204
    return


if __name__ == "__main__":

    run(app, host="127.0.0.1", port=12345, reloader=True, debug=True)
