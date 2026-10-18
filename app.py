#!/usr/bin/env python3

# AI: Except for djb2_hex all the code in this file has been implemented
# oldschool way by hand, just using AI tools as a search assistant.

import re
import math
import time

from statistics import mean, stdev, quantiles

from bottle import Bottle, response, request, run


mem = {}

app = Bottle()

valid_operations = ["add", "sub", "div", "mult", "sqrt", "mean", "std", "reset"]


def djb2_hex(text):
    """ Simple hash function given a text return hex hash
    " Daniel J. Bernstein is just awesome, just a tribute <3
    " http://www.cse.yorku.ca/~oz/hash.html
    """

    hash_val = 5381

    for byte in text.encode('utf-8'):
        hash_val = ((hash_val << 5) + hash_val) + byte
        hash_val &= 0xFFFFFFFF

    return f"{hash_val:08x}"


def create_session(request):
    """
    " Given a request returns a session_id
    """
    timestamp = str(time.time())
    client_ip = request.environ.get('REMOTE_ADDR', '')
    client_port = request.environ.get('REMOTE_PORT', '')

    return djb2_hex(f"{timestamp}:{client_ip}:{client_port}")


def store_session(session, value):
    """
    " Stores session value
    """
    mem[session] = value


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


@app.post("/session")
def create():
    timestamp = str(time.time())
    client_ip = request.environ.get('REMOTE_ADDR', '')
    client_port = request.environ.get('REMOTE_PORT', '')

    session = djb2_hex(f"{timestamp}:{client_ip}:{client_port}")

    response.status = 201
    base_url = request.url.rstrip('/')
    response.set_header('Location', f'{base_url}/{session}')

    return session


@app.route("/calculate/<numbers>/<operation>", method=['GET', 'POST'])
def calculate(numbers, operation):
    """
    " Given a list of numbers and an operation return the value:
    "   /calculate/1,2/add
    "
    "   200 OK
    "   3
    " GET just calculate
    " POST also create a session accumulating the given result
    """

    pattern = r'^[-+]?(?:\d+\.?\d*|\.\d+)(?:,[-+]?(?:\d+\.?\d*|\.\d+))*$'
    if not re.match(pattern, numbers):
        response.status = 422
        return "Error: invalid number(s)"

    if operation not in valid_operations:
        response.status = 409
        return "Error: not a valid operation"

    operands = [float(n) if '.' in n else int(n) for n in numbers.split(',')]

    if operation == 'add':
        result = sum(operands)

    if request.method == 'POST':
        session = create_session(request)
        store_session(session, result)

        response.status = 201
        base_url = request.url.rstrip('/')
        response.set_header('Location', f'{base_url}/session/{session}')

    else: # is GET
        response.status = 200

    return str(result)


@app.get("/session/<session>")
def get(session):
    return djb2_hex("Hello")


if __name__ == "__main__":
    run(app, host="127.0.0.1", port=12345, reloader=True, debug=True)
