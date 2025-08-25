import json
import uuid

class Message:
    def __init__(self, proto, mtype, from_node, to_node, ttl, payload, headers=None, msg_id=None):
        self.msg_id = msg_id or str(uuid.uuid4())  # ID único para evitar reenvíos duplicados
        self.proto = proto
        self.mtype = mtype
        self.from_node = from_node
        self.to_node = to_node
        self.ttl = ttl
        self.payload = payload
        self.headers = headers or {}

    def to_json(self):
        return json.dumps(self.__dict__)

    @staticmethod
    def from_json(data):
        return Message(**json.loads(data))