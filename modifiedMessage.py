import json
import uuid

class Message:
    def __init__(self, type=None, source=None, destination=None, hops=None, 
                 msg_id=None, from_node=None, to_node=None, **kwargs):
        """
        Ahora se usa 'type' en lugar de 'mtype' en la interfaz.
        """
        self.msg_id = msg_id or str(uuid.uuid4())
        self.mtype = type or kwargs.get('type')  # Internamente sigue llamándose mtype
        self.hops = hops
        
        # Determinar origen y destino según parámetros disponibles
        if from_node is not None and to_node is not None:
            origin = from_node
            dest = to_node
        elif source is not None and destination is not None:
            origin = source
            dest = destination
        elif 'from' in kwargs and 'to' in kwargs:
            origin = kwargs['from']
            dest = kwargs['to']
        else:
            raise ValueError("Debe especificar origen y destino usando alguno de estos formatos:\n"
                             "- from_node, to_node\n"
                             "- source, destination\n"
                             "- from, to (via kwargs)")

        setattr(self, 'from', origin)
        setattr(self, 'to', dest)
        self.from_node = origin
        self.to_node = dest

    def to_json(self):
        data = {
            'type': self.mtype,        # Exportamos como 'type'
            'from': getattr(self, 'from'),
            'to': getattr(self, 'to'),
            'hops': self.hops
        }
        return json.dumps(data)

    @staticmethod
    def from_json(data):
        msg_data = json.loads(data)
        if 'type' in msg_data:
            msg_data['mtype'] = msg_data['type']  # Normalizamos internamente
        if 'headers' in msg_data and isinstance(msg_data['headers'], list):
            if len(msg_data['headers']) > 0 and isinstance(msg_data['headers'][0], dict):
                combined_headers = {}
                for header_obj in msg_data['headers']:
                    combined_headers.update(header_obj)
                msg_data['headers'] = combined_headers
            else:
                msg_data['headers'] = {}
        return Message(**msg_data)

    def copy_for_forward(self, new_source):
        return Message(
            type=self.mtype,
            source=new_source,
            destination=getattr(self, 'to')
        )
    
    def get_from(self):
        return getattr(self, 'from')
    
    def get_to(self):
        return getattr(self, 'to')
    
    def _repr_(self):
        return f"Message(from={self.get_from()}, to={self.get_to()}, type={self.mtype})"
