import json
import uuid

class Message:
    def __init__(self, proto, mtype, source=None, destination=None, ttl=None, payload=None, 
                 headers=None, msg_id=None, from_node=None, to_node=None, **kwargs):
        """
        Constructor compatible con ambos formatos:
        - Message(proto, mtype, from_node=X, to_node=Y, ...)  # Formato original
        - Message(proto, mtype, source=X, destination=Y, ...)  # Formato nuevo (evita 'from')
        
        También puede recibir from/to via **kwargs para compatibilidad JSON
        """
        self.msg_id = msg_id or str(uuid.uuid4())
        self.proto = proto
        self.mtype = mtype
        self.ttl = ttl
        self.payload = payload
        self.headers = headers or {}
        
        # Determinar origen y destino según parámetros disponibles
        if from_node is not None and to_node is not None:
            # Formato original: from_node, to_node
            origin = from_node
            dest = to_node
        elif source is not None and destination is not None:
            # Formato nuevo: source, destination
            origin = source
            dest = destination
        elif 'from' in kwargs and 'to' in kwargs:
            # Formato desde JSON: from, to
            origin = kwargs['from']
            dest = kwargs['to']
        else:
            raise ValueError("Debe especificar origen y destino usando alguno de estos formatos:\n"
                           "- from_node, to_node\n"
                           "- source, destination\n"
                           "- from, to (via kwargs)")
        
        # Asignar a campos internos (usando setattr para evitar palabra reservada)
        setattr(self, 'from', origin)
        setattr(self, 'to', dest)
        
        # Mantener compatibilidad con código existente
        self.from_node = origin
        self.to_node = dest

    def to_json(self):
        """Exporta usando formato 'from'/'to' para compatibilidad"""
        data = {
            'msg_id': self.msg_id,
            'proto': self.proto,
            'mtype': self.mtype,
            'from': getattr(self, 'from'),
            'to': getattr(self, 'to'),
            'ttl': self.ttl,
            'payload': self.payload,
            'headers': self.headers
        }
        return json.dumps(data)

    @staticmethod
    def from_json(data):
        """Crea Message desde JSON que puede usar 'from'/'to' o 'from_node'/'to_node'"""
        msg_data = json.loads(data)
        
        # Compatibilidad con formato del laboratorio: 'type' -> 'mtype'
        if 'type' in msg_data and 'mtype' not in msg_data:
            msg_data['mtype'] = msg_data['type']
            
        # Normalizar headers (array -> dict si es necesario)
        if 'headers' in msg_data and isinstance(msg_data['headers'], list):
            if len(msg_data['headers']) > 0 and isinstance(msg_data['headers'][0], dict):
                # Combinar múltiples objetos en headers
                combined_headers = {}
                for header_obj in msg_data['headers']:
                    combined_headers.update(header_obj)
                msg_data['headers'] = combined_headers
            else:
                msg_data['headers'] = {}
                
        return Message(**msg_data)

    def copy_for_forward(self, new_source, _next_hop):
        """
        Crea copia para reenvío. Compatible con ambos formatos.
        
        Args:
            new_source: El nodo que está reenviando el mensaje
            _next_hop: Siguiente nodo (no se usa en el mensaje)
        """
        return Message(
            proto=self.proto,
            mtype=self.mtype,
            source=new_source,                    # Nuevo origen
            destination=getattr(self, 'to'),      # Mantiene destino
            ttl=self.ttl,
            payload=self.payload,
            headers=self.headers.copy(),
            msg_id=self.msg_id
        )
    
    # Métodos de conveniencia
    def get_from(self):
        """Obtiene el origen del mensaje"""
        return getattr(self, 'from')
    
    def get_to(self):
        """Obtiene el destino del mensaje"""
        return getattr(self, 'to')
    
    def __repr__(self):
        return f"Message(from={self.get_from()}, to={self.get_to()}, type={self.mtype}, payload={self.payload})"