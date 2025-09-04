from MessageStruct import Message
import heapq
import time

class Node:
    def __init__(self, name, neighbors=None, mode="flooding", graph=None):
        self.name = name
        self.neighbors = neighbors or []      # lista de nodos vecinos (objetos Node)
        self.received_msgs = set()            # IDs de mensajes ya recibidos
        self.mode = mode                      # "flooding" o "dijkstra"
        self.graph = graph or {}              # topología completa para Dijkstra
        self.prev = {}                        # diccionario prev para backtracking
        self.lsp_database = {}        # Base de datos de LSPs recibidos
        self.sequence_number = 0      # Número de secuencia para LSPs propios
        self.neighbor_costs = {}      # Costos hacia vecinos directos
        self.topology_graph = {}      # Topología construida desde LSPs
        if self.mode == "dijkstra" and self.graph:
            self._dijkstra()

        if self.mode == "lsr":
            self._initialize_lsr()

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

    def _initialize_lsr(self):
        """Inicializa LSR: descubre vecinos y costos"""
        print(f"[{self.name}] Inicializando LSR...")
        
        # Simular costos a vecinos (en realidad se mediría con HELLO/PING)
        for neighbor in self.neighbors:
            # Por simplicidad, asignar costo 1 a todos los vecinos
            # En implementación real, se mediría latencia/ancho de banda
            self.neighbor_costs[neighbor.name] = 1
        
        # Crear y enviar LSP inicial
        self._create_and_flood_lsp()

    def _create_and_flood_lsp(self):
        """Crea un LSP con info de enlaces propios y lo propaga"""
        self.sequence_number += 1
        
        # Crear LSP con información de enlaces
        lsp = {
            "node": self.name,
            "sequence": self.sequence_number,
            "timestamp": time.time(),
            "links": self.neighbor_costs.copy()
        }
        
        # Agregar a nuestra propia base de datos
        self.lsp_database[self.name] = lsp
        
        # Crear mensaje LSP para flooding
        lsp_message = Message(
            proto="lsr",
            mtype="lsp",
            from_node=self.name,
            to_node="broadcast",  # Broadcasting
            ttl=10,
            payload=lsp,
            msg_id=f"lsp_{self.name}_{self.sequence_number}"
        )
        
        print(f"[{self.name}] Creando LSP: {lsp}")
        
        # Hacer flood del LSP
        self._flood_lsp(lsp_message, incoming=None)
        
        # Reconstruir topología y recalcular rutas
        self._rebuild_topology()

    def _flood_lsp(self, lsp_message: Message, incoming):
        """Propaga LSP a todos los vecinos (excepto el que nos lo envió)"""
        if lsp_message.msg_id in self.received_msgs:
            return  
            
        self.received_msgs.add(lsp_message.msg_id)
        lsp_data = lsp_message.payload
        sender_node = lsp_data["node"]
        
        # Verificar si es más reciente (incluyendo timestamp como desempate)
        should_update = False
        if sender_node not in self.lsp_database:
            should_update = True
        else:
            existing = self.lsp_database[sender_node]
            if (lsp_data["sequence"] > existing["sequence"] or 
                (lsp_data["sequence"] == existing["sequence"] and 
                lsp_data["timestamp"] > existing["timestamp"])):
                should_update = True
        
        if should_update:
            print(f"[{self.name}] Recibido LSP de {sender_node}: {lsp_data['links']}")
            self.lsp_database[sender_node] = lsp_data
            self._rebuild_topology()
            
            # Continuar flooding
            lsp_message.ttl -= 1
            if lsp_message.ttl > 0:
                for neighbor in self.neighbors:
                    if neighbor.name != incoming:
                        print(f"[{self.name}] Propagando LSP → {neighbor.name}")
                        neighbor._flood_lsp(lsp_message, incoming=self.name)
                        
    def _rebuild_topology(self):
        """Reconstruye la topología completa desde los LSPs"""
        self.topology_graph = {}
        
        # Construir grafo desde todos los LSPs conocidos
        for node_name, lsp in self.lsp_database.items():
            self.topology_graph[node_name] = lsp["links"].copy()
        
        print(f"[{self.name}] Topología reconstruida: {self.topology_graph}")
        
        # Ejecutar Dijkstra sobre la nueva topología
        if self.topology_graph:
            self._dijkstra_lsr()

    def _dijkstra_lsr(self):
        """Ejecuta Dijkstra sobre la topología construida por LSR"""
        import heapq
        
        dist = {n: float("inf") for n in self.topology_graph}
        prev = {n: None for n in self.topology_graph}
        dist[self.name] = 0
        pq = [(0, self.name)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            
            for v, w in self.topology_graph.get(u, {}).items():
                if v in dist and dist[v] > d + w:
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        self.prev = prev
        print(f"[{self.name}] LSR - Rutas calculadas: {self.prev}")

    def _route_lsr(self, message: Message):
        """Enrutamiento usando tabla calculada por LSR"""
        if message.to_node == self.name:
            print(f"[{self.name}] RECIBÍ mensaje DESTINO: {message.payload}")
            return

        # Usar la tabla prev calculada por LSR
        if message.to_node not in self.prev:
            print(f"[{self.name}] No hay ruta a {message.to_node}")
            return

        # Construir ruta completa
        path = []
        current = message.to_node
        while current != self.name:
            path.append(current)
            current = self.prev[current]
            if current is None:
                print(f"[{self.name}] Ruta incompleta a {message.to_node}")
                return
        path.append(self.name)
        path.reverse()

        # Encontrar siguiente salto
        next_hop_name = path[1]
        next_hop = next(n for n in self.neighbors if n.name == next_hop_name)

        msg_copy = message.copy_for_forward(self.name, next_hop.name)
        print(f"[{self.name}] LSR ROUTE {message.to_node} → {next_hop.name} (ruta: {path})")
        next_hop.receive_message(msg_copy)

    def receive_message(self, message: Message):
        """Recibe mensaje según el protocolo"""
        try:
            if message.mtype == "lsp":
                self._flood_lsp(message, incoming=message.from_node)
            elif message.mtype == "message":
                if self.mode == "lsr":
                    self._route_lsr(message)
                elif self.mode == "flooding":
                    self._flood(message, incoming=message.from_node)
                elif self.mode == "dijkstra":
                    self._route(message)
            else:
                print(f"[{self.name}] Tipo de mensaje desconocido: {message.mtype}")
        except Exception as e:
            print(f"[{self.name}] Error procesando mensaje: {e}")
            
    def send_message(self, message: Message):
        """Envía mensaje según el modo"""
        if self.mode == "flooding":
            print(f"[{self.name}] Enviando mensaje FLOOD: {message.payload}")
            self._flood(message, incoming=None)
        elif self.mode == "dijkstra":
            print(f"[{self.name}] Enviando mensaje DIJKSTRA: {message.payload}")
            self._route(message)
        elif self.mode == "lsr":
            print(f"[{self.name}] Enviando mensaje LSR: {message.payload}")
            self._route_lsr(message)

    def trigger_lsp_update(self):
        """Fuerza actualización de LSP (útil cuando cambia la red)"""
        if self.mode == "lsr":
            print(f"[{self.name}] Actualizando LSP...")
            self._create_and_flood_lsp()


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
    
    # ------------------ EJEMPLO LSR ------------------
    # Inicializar LSR en todos los nodos
    for node in [A, B, C, D]:
        node._initialize_lsr()
    # Esperar un poco para que se estabilice
    print("\n--- LSR inicializado, enviando mensaje ---\n")
    
    # Crear mensaje de datos
    msg_lsr = Message(
        proto="lsr",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="¡Hola desde A usando LSR!"
    )

    # A envía mensaje
    A.send_message(msg_lsr)

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
