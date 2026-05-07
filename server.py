import os
from flask import Flask, send_from_directory
import json

app = Flask(__name__)

# Load config to get the save directory
with open('config.json', 'r') as f:
    config = json.load(f)

SAVE_DIR = config.get('save_directory', 'screenshots')

@app.route('/<path:filename>')
def serve_image(filename):
    return send_from_directory(os.path.abspath(SAVE_DIR), filename)

def run_server(port):
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    app.run(host='127.0.0.1', port=port, threaded=True)

if __name__ == '__main__':
    with open('config.json', 'r') as f:
        config = json.load(f)
    run_server(config.get('port', 8892))