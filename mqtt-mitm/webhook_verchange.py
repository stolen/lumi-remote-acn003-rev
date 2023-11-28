#!/bin/python
from flask import Flask, json, request

api = Flask(__name__)

@api.route('/verchange', methods=['POST'])
def verchange():
    req = request.get_json(force=True)
    print(req)
    topic = req['topic']
    payload = json.loads(req['payload'])
    if (topic[0:3] == "gw/") and (topic[19:] == "/MessageReceived") and ('APSPlayload' in payload):
        aps = payload['APSPlayload']
        # 0x1D5F11A5030E0104030A302E302E305F30303039
        # 0x1D5F1184030E0104030A302E302E305F30303039
        # 1D5F11 84 030E010403 0A302E302E305F30303039
        #   * 1D5F11 -- magic
        #   * 84 -- seq
        #   * 030E010403 -- ???
        #   * 0A -- len, "0.0.0-0009"
        if (aps[0:8] == "0x1D5F11") and (aps[20:42] == "0A302E302E305F30303039"):
            payload['APSPlayload'] = aps.replace('0A302E302E305F30303039', '0A302E302E305F30303031')
            return json.dumps({"result":"ok", "modifiers": {"payload": json.dumps(payload)}})
    return json.dumps({"result":"ok"})

if __name__ == '__main__':
    api.run()
