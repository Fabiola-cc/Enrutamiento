from MessageStruct import Message
import heapq

class Node:
    def __init__(self, name, neighbors=None, mode="flooding", graph=None):
        self.name = name
        self.neighbors = neighbors or []      # lista de nodos vecinos (objetos Node)
        self.received_msgs = set()            # IDs de mensajes ya recibidos
        self.mode = mode                      # "flooding" o "dijkstra"
        self.graph = graph or {}              # topología completa para Dijkstra
        self.prev = {}                        # diccionario prev para backtracking
        if self.mode == "dijkstra" and self.graph:
            self._dijkstra()

    def add_neighbor(self, neighbor):
        self.neighbors.append(neighbor)

    def _dijkstra(self):
        """Calcula distancias mínimas y prev para backtracking"""
        dist = {n: float("inf") for n in self.graph}
        prev = {n: None for n in self.graph}
        dist[self.name] = 0
        pq = [(0, self.name)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, w in self.graph.get(u, {}).items():
                if dist[v] > d + w:
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        self.prev = prev
        print(f"[{self.name}] Distancias calculadas (prev): {self.prev}")

    def send_message(self, message: Message):
        """Envia mensaje según el modo"""
        if self.mode == "flooding":
            print(f"[{self.name}] Enviando mensaje FLOOD: {message.payload}")
            self._flood(message, incoming=None)
        elif self.mode == "dijkstra":
            print(f"[{self.name}] Enviando mensaje DIJKSTRA: {message.payload}")
            self._route(message)

    def _flood(self, message: Message, incoming):
        if message.ttl <= 0 or message.msg_id in self.received_msgs:
            return
        self.received_msgs.add(message.msg_id)

        if message.to_node == self.name:
            print(f"[{self.name}] Recibí mensaje DESTINO: {message.payload}")

        message.ttl -= 1
        for neighbor in self.neighbors:
            if neighbor.name != incoming:
                msg_copy = message.copy_for_forward(self.name, neighbor.name)
                print(f"[{self.name}] FLOOD → {neighbor.name}")
                neighbor._flood(msg_copy, incoming=self.name)

    def _route(self, message: Message):
        if message.to_node == self.name:
            print(f"[{self.name}] Recibí mensaje DESTINO: {message.payload}")
            return

        # Construir ruta completa con backtracking
        path = []
        current = message.to_node
        while current != self.name:
            path.append(current)
            if current not in self.prev:
                print(f"[{self.name}] No hay ruta a {message.to_node}")
                return
            current = self.prev[current]
        path.append(self.name)
        path.reverse()  # ruta desde self hasta destino

        # El siguiente salto es el primer nodo después de este nodo
        next_hop_name = path[1]
        next_hop = next(n for n in self.neighbors if n.name == next_hop_name)

        msg_copy = message.copy_for_forward(self.name, next_hop.name)
        print(f"[{self.name}] ROUTE {message.to_node} → {next_hop.name} (ruta completa: {path})")
        next_hop._route(msg_copy)


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

    # Topología con pesos (para Dijkstra)
    graph = {
        "A": {"B": 1, "C": 2},
        "B": {"A": 1, "D": 4},
        "C": {"A": 2, "D": 1},
        "D": {"B": 4, "C": 1}
    }

    # ------------------ EJEMPLO FLOODING ------------------
    print("\n--- EJEMPLO FLOODING ---\n")
    # Configurar modo flooding
    for node in [A, B, C, D]:
        node.mode = "flooding"
        node.received_msgs.clear()  # limpiar mensajes previos

    # Crear mensaje flooding
    msg_flood = Message(
        proto="flooding",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=5,
        payload="Hola desde A usando FLOODING!"
    )

    # A inicia el flooding
    A.send_message(msg_flood)

    # ------------------ EJEMPLO DIJKSTRA ------------------
    print("\n--- EJEMPLO DIJKSTRA ---\n")
    # Configurar modo Dijkstra
    for node in [A, B, C, D]:
        node.mode = "dijkstra"
        node.graph = graph
        node.prev.clear()        # limpiar prev previo
        node._dijkstra()
        node.received_msgs.clear()  # limpiar mensajes previos

    # Crear mensaje Dijkstra
    msg_dijk = Message(
        proto="dijkstra",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="Hola desde A usando DIJKSTRA!"
    )

    # A envía mensaje Dijkstra
    A.send_message(msg_dijk)
