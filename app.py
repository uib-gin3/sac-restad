import time

from bottle import Bottle, response, request, run

mem = {}

app = Bottle()

def djb2_hex(text: str) -> str:
    # Daniel J. Bernstein is just awesome, just sending him some love <3
    # http://www.cse.yorku.ca/~oz/hash.html
    hash_val = 5381

    for byte in text.encode('utf-8'):
        hash_val = ((hash_val << 5) + hash_val) + byte
        hash_val &= 0xFFFFFFFF

    return f"{hash_val:08x}"


@app.hook('before_request')
def set_default_headers():
    """
    " Set common things to all requests
    """
    response.content_type = 'text/plain; charset=utf-8'
    request.environ['REQUEST_START_TIME'] = time.time()


@app.hook('after_request')
def set_final_headers():
    start_time = request.environ.get('REQUEST_START_TIME')
    if start_time:
        elapsed_time = time.time() - start_time
        response.set_header('X-Response-Time', f"{elapsed_time:.4f}s")


@app.post("/")
def create():
    timestamp = str(time.time())
    client_ip = request.environ.get('REMOTE_ADDR', '')
    client_port = request.environ.get('REMOTE_PORT', '')

    session = djb2_hex(f"{timestamp}:{client_ip}:{client_port}")

    response.status = 201
    base_url = request.url.rstrip('/')
    response.set_header('Location', f'{base_url}/{session}')

    return session


@app.get("/<session>")
def get(session):
    return djb2_hex("Hello")


if __name__ == "__main__":
    run(app, host="127.0.0.1", port=12345, reloader=True)
