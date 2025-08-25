from MessageStruct import Message

class Node:
    def __init__(self, name, neighbors=None):
        self.name = name
        self.neighbors = neighbors or []  # lista de nodos vecinos
        self.received_msgs = set()        # almacenar IDs de mensajes ya recibidos

    def add_neighbor(self, neighbor):
        self.neighbors.append(neighbor)

    def send_message(self, message: Message):
        """Envia un mensaje inicial a todos los vecinos (flooding root)."""
        print(f"[{self.name}] Enviando mensaje a vecinos: {message.payload}")
        self._flood(message, incoming=None)

    def _flood(self, message: Message, incoming):
        """Reenvío del mensaje a vecinos excepto el que lo envió."""
        if message.ttl <= 0:
            return

        if message.msg_id in self.received_msgs:
            print(f"[{self.name}] Recibí mensaje ya guardado")
            return  # ya lo procesé antes

        # Registrar mensaje recibido
        self.received_msgs.add(message.msg_id)

        # Si soy el destino, lo proceso
        if message.to_node == self.name:
            print(f"[{self.name}] Recibí mensaje DESTINO: {message.payload}")

        # Decrementar TTL
        message.ttl -= 1

        # Reenviar a todos los vecinos excepto el entrante
        for neighbor in self.neighbors:
            if neighbor.name != incoming:  
                # Actualizar origen y destino
                message.from_node = self.name
                message.to_node = neighbor.name
                # Enviar mensaje
                print(f"[{self.name}] Reenviando a {neighbor.name}")
                neighbor._flood(message, incoming=self.name)


# ---------------- Ejemplo de uso ----------------
if __name__ == "__main__":
    # Crear nodos
    A = Node("A")
    B = Node("B")
    C = Node("C")
    D = Node("D")

    # Conectar vecinos
    A.add_neighbor(B)
    A.add_neighbor(C)
    B.add_neighbor(A)
    B.add_neighbor(D)
    C.add_neighbor(A)
    C.add_neighbor(D)
    D.add_neighbor(B)
    D.add_neighbor(C)

    # Crear mensaje flooding
    msg = Message(
        proto="flooding",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=5,
        payload="Hola desde A!"
    )

    # A inicia el flooding
    A.send_message(msg)
