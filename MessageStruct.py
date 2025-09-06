import json
import uuid

class Message:
    def __init__(self, proto, mtype, from_node, to_node, ttl, payload, headers=None, msg_id=None):
        self.msg_id = msg_id or str(uuid.uuid4())
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

    # ------------------- nuevo -------------------
    def copy_for_forward(self, from_node, _next_hop):
        return Message(
            proto=self.proto,
            mtype=self.mtype,
            from_node=from_node,
            to_node=self.to_node,    
            ttl=self.ttl,
            payload=self.payload,
            headers=self.headers.copy(),
            msg_id=self.msg_id
        )

