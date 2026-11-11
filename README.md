# restad REST Daemon that knows how to "restar"

- Rest -> Application Programming Interface & Representational State Transfer
- Resta -> Subtract in Spanish
- Restad -> Plural of subtract in Spanish (imperative).

Unix daemons finalize with a `d`: we ask a bunch of Unix processes running as
a daemon to act as a REST API able to `restar`, so Unix processes `restad`
these numbers.


## Abstract

A simple REST API implemented with Python + Bottle to implement a basic
calculator. Restad can run by itself as a single Python process, multiprocess
with Gunicorn and optionally use Redis as a backend when deployed in different
containers / servers.

The development has been done following KISS (Keep It Simple, Stupid) and UNIX
philosophy (do one thing and do it well). As Redis already needed a container,
a Dockerfile and docker-compose.yml have been added as well.


## Assignment

Implement a **calculator** as a REST service, in any language you choose:
  add, sub, div, mult, sqrt, mean, std and reset.

The user must keep their last value, which is why the special `reset` operation
exists.

Justify the design and implementation decisions taken under the SD (shared-state)
paradigm.

**Delivery**: in AD (the campus delivery system), include the link to the (publicly
accessible) repository containing the source code and the relevant descriptions.


## Setup

This project has been tested on Debian 13 and Docker 29.9.0 with the compose plugin.

It should just need bash, Docker and Docker Compose.

If running without Redis, containers can be avoided and uv / uvx used. Tested
with 0.11.8.


## Usage example

### Some useful alias

    alias GET="uvx --from httpie http GET"
    alias POST="uvx --from httpie http POST"
    alias PUT="uvx --from httpie http PUT"
    alias PATCH="uvx --from httpie http PATCH"
    alias DELETE="uvx --from httpie http DELETE"

### Run simple way: single process no Redis

    uv run --with bottle==0.13.4 python app.py

### Production mode: multiprocess with Gunicorn + Redis

    docker compose up

### Test

    PUT localhost:12345/calc/my-calc --raw 3,4,5,6
    PATCH localhost:12345/calc/my-calc --raw 7,8,9
    GET localhost:12345/calc/my-calc/add
    # Will respond the meaning of life (42)

### Benchmark

   uv run ./restad-bench -c 5 -r 10 -d 30


Without uv it is also fine, as restad-bench is all Python stdlib.


## The strike mode (sac-strike)

restad doubles as the calculator workforce of the
[sac-strike](https://github.com/uib-gin3/sac-strike) assignment ("The
calculators' strike"): a leader elected through etcd delegates operations
to its colleagues, nodes can go on strike and every leader lives on a
burnout countdown. Everything is switched on by the `STRIKE_` environment
variables; without them restad behaves exactly as described above.

### New endpoints

    POST localhost:12345/strike
    # on strike for 4.2s
    # While on strike every calculation answers 418 I'm a teapot
    # and a leader steps down immediately.

    GET localhost:12345/health
    # healthy, leader: node3
    # 200 when the node can serve, 418 (with the reason in the body)
    # when it is on strike or burned out. It always answers, even when
    # on strike, so whoever watches can see the recovery.

### New headers

    X-Served-By: node2   the hostname of the node that computed
    X-Leaded-By: node1   the leader that orchestrated (when there was one)

### Environment variables

    STRIKE_ETCD                 host[:port] of etcd; it alone activates
                                the distributed mode
    STRIKE_PORT                 the port this node serves on, for its
                                workforce registration (12345)
    STRIKE_LEADING_OVERHEAD     the leader computes itself with
                                probability 1/N - (1/N * overhead),
                                N being the size of the workforce
    STRIKE_ALGORITHM            random (default), robust (delegate to
                                the colleague with the fewest failures)
                                or fastest (lowest average response
                                time), chosen from the redis counters
    STRIKE_MIN_TIME             strike window, minimum (2s)
    STRIKE_MAX_TIME             strike window, maximum (6s)
    STRIKE_BURNOUT_MIN_TIME     burnout countdown, minimum (8s)
    STRIKE_BURNOUT_MAX_TIME     burnout countdown, maximum (20s)
    STRIKE_RETRY                delegation attempts before giving up (5)
    STRIKE_TTL                  lease of the etcd leader and workforce
                                keys (4s)
    STRIKE_TIMEOUT              timeout of a delegated request (5s)

### Metrics in redis

The leader keeps track of who responded, how long it took and whether the
operation failed:

    strike:ok:<node>     successful answers per node
    strike:fail:<node>   failed answers per node (418, 5xx, timeouts)
    strike:time:<node>   accumulated seconds per node (the robust and
                         fastest algorithms read these counters)
    strike:self          operations the leader computed itself
    strike:delegated     operations delegated to a colleague
    strike:events        log of elections, step downs, strikes, burnouts
                         and delegation failures

### Notes

The strike and leader state lives in the process memory, so the gunicorn
deployment is now a single threaded worker (`--workers 1 --threads 8`)
instead of four sync workers. Same API, the state just does not need to
be synchronised between processes.

There is no background loop: the requests themselves drive everything.
Two etcd key families hold the whole shared state, both with leases:

    strike/workforce/<hostname>   the http endpoint of each node
    strike/leader                 the hostname of the leader

Every request re-asserts its node's workforce membership (throttled to
about twice per TTL) and asks etcd who leads. A leaderless workforce
elects a leader on the next request with a compare-and-swap; the leader
renews its lease while requests come; a struck or burned out leader
deletes the key and steps down the moment a request finds it; and if a
leader simply dies, the lease expires and the next request elects
somebody else. The burnout countdown is evaluated the same way, so it
fires on the first request after it expires. An idle fleet has no leader
and lets memberships lapse; the first request that shows up starts
everything again, and while users are being served there is (almost)
always a leader.

When etcd is unreachable a node behaves as a follower and always serves
locally; the workforce list falls back to the last known one. No etcd
hiccup ever breaks a calculation.


## Server interface

Tried to follow HTTP Verb semantics:
https://www.rfc-editor.org/rfc/rfc9110.html

Create a calculus with POST, you can send the first list of numbers in the payload:

    POST localhost:12345/calc --raw 3,4,5,6
    # Will return the calc-id as response and in the Location header

You can also create a calculus by PUTing all the content into the id you define.

    PUT localhost:12345/calc/my-calc --raw 3,4,5,6

Numbers can be added with PATCH

    PATCH localhost:12345/calc/my-calc --raw 7,8,9
    # <some-id> will contain the list 3,4,5,6,7,8,9


You also can GET the result (without modifying the calc), appending an operation

    GET localhost:12345/calc/my-calc/add
    # Will respond 42

You can also GET the content without an operation, it just responds with the
number list.

    GET localhost:12345/calc/my-calc
    # Will respond 3,4,5,6,7,8,9

You can also get the result POSTing it into a consolidated result:

    POST localhost:12345/calc/my-calc/add
    # Will respond 42

    GET localhost:12345/calc/my-calc
    # Will respond 42 not the number list

Finally you can DELETE the calc when no longer needed.

    DELETE localhost:12345/calc/my-calc
    # Will delete it

    GET localhost:12345/calc/my-calc
    # Will respond 404


## Design decisions

No versioning for the REST API, it is too simple.

Normally I would go Flask or Django REST framework but I will go even simpler
with Bottle.

JSON is really popular in REST APIs but is just a convention, is not really
needed, this API is not JSON, just plain strings. Numbers can be separated by
commas to be lists.

To avoid collisions I used a hash based on timestamp + source IP + source
port + some randomness. Hash function selected: djb2, not because the best just
because DJB is awesome and always deserves credit.

The implementation has a dual way to operate: with standard Python shared
memory or Redis. Locks also support both backends.

Let's imagine an entity which is 'number list' so tried to understand verbs
from https://www.rfc-editor.org/rfc/rfc9110.html and use them properly on it.


## Observations

Table run and generated with MiniMax M3.1 OpenCode when asked to compare
sac-restad with sac-sock-calc

|                             | socket `sac-sock-calc` | REST Bottle (1 process) | REST Gunicorn 4w + Redis  |
|-----------------------------|------------------------|-------------------------|---------------------------|
| offered load                | 50 req/s               | 50 ops/s (150 req/s)    | 50 ops/s (150 req/s)      |
| served                      | 1313 req (43.7 req/s)  | 1475 ops / 4425 req     | 1373 ops / 4119 req       |
| throughput                  | 43.7 req/s             | 49.2 ops/s (147.5 req/s)| 45.8 ops/s (137.3 req/s)  |
| errors                      | 0                      | 0                       | 0                         |
| TCP connections             | 5 (one per client)     | 4425 (one per request)  | 4119 (one per request)    |
| response time p50           | 4.30 ms                | 1.67 ms                 | 2.35 ms                   |
| response time p95           | 44.91 ms               | 2.54 ms                 | 3.26 ms                   |
| response time p99           | 47.63 ms               | 3.24 ms                 | 3.63 ms                   |
| response time max           | 50.36 ms               | 4.56 ms                 | 7.10 ms                   |
| server's own clock (avg/p95)| 0.53 / 1.91 ms         | 0.42 / 0.70 ms          | 0.65 / 1.00 ms            |
| bytes sent / received       | 127 249 / 27 658       | 455 803 / 871 245       | 427 158 / 777 238         |

I have to confess that I'm not double checking it to arrive on the delivery
deadline.

Seeing that result I would say:

- Even sac-sock-calc has fewer layers it was poorly implemented and optimized
so gunicorn is way faster even having way more layers.
- There are no significant differences between single Python process and
multiprocess with Gunicorn probably the bottleneck is the benchmark client
itself.
- Redis and Gunicorn seem to increase response time. More layers more ms,
but not crazy at all. With bigger requests won't be noticeable.

## AI usage

None of the text intended to be read by a human has been generated by an AI
tool, whereas most of the texts (code) intended to be processed by a
machine have been generated by AI Agents (OpenCode).

Nowadays it is extremely easy to produce tons of text. I could ask OpenCode to
write this file and look amazing, but I've tried to keep the assignment within
its bounds to just show the ability to develop a REST API and put some thought
into it.

AI tools have been used to check spelling and grammar, you can see original text on
second-to-last commit. Also few final manual edits were done.

This approach is to avoid being a [meat proxy](https://gruhn.me/blog/2026-08-03/).

- gemini-3.1-pro (web): Translate <assignment title> to English
- gemini-3.1-pro (web): Many lookups of information about Python libraries
and REST concepts
- gemini-3.1-pro (web): Implement djb2 hash function
- MiniMax-M3.1-flash (opencode): Develop restad-client, restad-test,
restad-bench & restadapi.py
- MiniMax-M3.1-flash (opencode): Run benchmark to compare sac-sock-calc
and sac-restad
- MiniMax-M3.1-flash (opencode): Can you check spell and grammar of README.md.
Suggest the minimal changes keeping the style.
- MiniMax-M3.1-flash (opencode): Can you check spell and grammar of the
comments of (not code) of restad-server. Suggest the minimal changes keeping
the style.
- GLM-5.3-flash (opencode): Implement the strike mode (etcd leader
election, delegation, strikes and burnouts) and etcdapi.py for the
sac-strike assignment.
