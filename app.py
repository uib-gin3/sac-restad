#!/usr/bin/env python3

# AI: Except for djb2_hex all the code in this file has been implemented
# oldschool way by hand, just using AI tools as a search assistant.

import re
import time
import random
import operator

from math import sqrt
from functools import reduce
from statistics import mean, stdev, quantiles, StatisticsError

from bottle import Bottle, response, request, run


mem = {}

app = Bottle()


# Operations are not important, we want to focus on the 
# API side so: lets be compact and hacky, which is fun yet not convinient
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


def djb2_hex(text):
    """ Simple hash function given a text return hex hash.
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
    " Hashing some connection elements + random to avoid colisions.
    """
    timestamp = str(time.time())
    client_ip = request.environ.get('REMOTE_ADDR', '')
    client_port = request.environ.get('REMOTE_PORT', '')
    rnd = random.random()

    return djb2_hex(f"{timestamp}:{client_ip}:{client_port}:{rnd}")


def store_session(session, value, external=False):
    """
    " Stores session value
    " If external is false it assumed that a single process is doing
    " the work so just a shared dict is fine.
    " If shared is true we use an external shared memory across
    " all processes.
    """

    if not external:
        mem[session] = value
        return # Finished if not shared, simple and easy

    # TODO shared=True


def get_session(session, shared=False):

    if not shared:
        return mem[session]

    # TODO shared=True


def parse_operands():
    """
    " Extract and parse the operands from request body
    " @return a dict with:
    "   data -> with the list of operands (if no error)
    "   status -> with the status code to be given if error
    "   error -> with the error Message
    """
    parsed = {}

    try:
        raw_data = request.body.read().decode('utf-8')
    except UnicodeDecodeError as exc:
        prased['status'] = 400
        parsed['error'] = str(exc)
        return parsed

    # Thanks AI for writting sucha good regex :D (hope it has no bugs)
    pattern = r'^[-+]?(?:\d+\.?\d*|\.\d+)(?:,[-+]?(?:\d+\.?\d*|\.\d+))*$'
    if not re.match(pattern, raw_data):
        parsed['status'] = 400
        parsed['error'] = "Invalid number(s)"
        return parsed

    return {
        'data': [float(n) if '.' in n else int(n) for n in raw_data.split(',')]
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


# POST creates and generates id
@app.post("/calc")
# PUT is idempotent user chooses id
@app.put("/calc/<calc_id>")
def create(calc_id=None):
    """
    " Create a new calculus adding the payload of comma separaed numbers
    " (if given). Will return the calc-id to use in futher requests.
    "
    "   /calculate
    "   body: 1,2
    "
    "   200 OK
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
    base_url = request.url.strip('/')
    response.set_header('Location', f'{base_url}/{calc_id}')

    return str(calc_id)


@app.patch("/calc/<calc_id>")
def update(calc_id):
    """
    " Add operands to an existng calculus as a list of comma separaed numbers.
    " Will return the current amount of operands.
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


    # TODO do with lock!
    try:
        operands = get_session(calc_id)
    except KeyError:
        response.status = 404
        return f'Error: calc {calc_id} does not exists'

    operands.extend(parsed['data'])
    store_session(calc_id, operands)
    # END TODO LOCK

    response.status = 200
    return str(len(operands))


@app.get("/calc/<calc_id>")
def get(calc_id):

    try:
        data = get_session(calc_id)
    except KeyError:
        response.status = 404
        return f'Error: calc {calc_id} does not exists'

    return ",".join([str(x) for x in data]) 


@app.route("/calc/<calc_id>/<operation>", method=['GET', 'POST'])
def calculate(calc_id, operation):
    """
    " Returns the desired operatin applied to the stored operand list
    " Does not modifyies the list (PUT would)
    "   /calc/31f6266f/add
    "
    "   200 OK
    "   3
    """

    if operation not in operations.keys():
        response.status = 409
        return "Error: not a valid operation"

    try:
        operands = get_session(calc_id)
    except KeyError:
        response.status = 404
        return f'Error: calc {calc_id} does not exists'

    try:
        result = operations[operation](operands)
    except (ArithmeticError, StatisticsError, TypeError) as exc:
        response.status = 422
        return f"Error: {exc}"

    if request.method == 'POST':
        store_session(calc_id, [result])

    response.status = 200

    return str(result)


if __name__ == "__main__":
    run(app, host="127.0.0.1", port=12345, reloader=True, debug=True)
