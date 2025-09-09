from MessageStruct import Message
import heapq
import time
import asyncio

class Node:
    def __init__(self, name, neighbors=None, mode="flooding", graph=None):
        self.name = name
        self.neighbors = neighbors or []      # lista de nodos vecinos (objetos Node)
        self.received_msgs = set()            # IDs de mensajes ya recibidos
        self.mode = mode                      # "flooding" o "dijkstra" o "lsr"
        self.graph = graph or {}              # topología completa para Dijkstra
        self.prev = {}                        # diccionario prev para backtracking
        self.lsp_database = {}                # Base de datos de LSPs recibidos
        self.sequence_number = 0              # Número de secuencia para LSPs propios
        self.neighbor_costs = {}              # Costos hacia vecinos directos
        self.topology_graph = {}              # Topología construida desde LSPs

        if self.mode == "dijkstra" and self.graph:
            self._dijkstra()

    def add_neighbor(self, neighbor):
        if neighbor not in self.neighbors:
            self.neighbors.append(neighbor)

    def _dijkstra(self):
        """Calcula distancias mínimas y prev para backtracking"""
        if not self.graph:
            print(f"[{self.name}] No hay grafo para calcular Dijkstra")
            return

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

    def _flood(self, message: Message, incoming):
        """Algoritmo de flooding"""
        if message.ttl <= 0 or message.msg_id in self.received_msgs:
            return
        self.received_msgs.add(message.msg_id)

        if message.to_node == self.name:
            print(f"[{self.name}]  RECIBÍ MENSAJE DESTINO: {message.payload}")
            return  # No reenviar si soy el destino

        message.ttl -= 1
        for neighbor in self.neighbors:
            if neighbor.name != incoming:
                msg_copy = message.copy_for_forward(self.name, neighbor.name)
                print(f"[{self.name}] FLOOD → {neighbor.name}")
                neighbor._flood(msg_copy, incoming=self.name)

    def _route(self, message: Message):
        """Enrutamiento Dijkstra"""
        if message.to_node == self.name:
            print(f"[{self.name}]  RECIBÍ MENSAJE DESTINO: {message.payload}")
            return

        if message.to_node not in self.prev:
            print(f"[{self.name}]  No hay ruta a {message.to_node}")
            return
            
        # Reconstruir la ruta desde este nodo hasta el destino
        path = []
        current = message.to_node

        while current is not None and current != self.name:
            path.append(current)
            current = self.prev.get(current)
        if current is None:
            print(f"[{self.name}]  No hay ruta a {message.to_node}")
            return

        path.append(self.name)
        path.reverse()  # ahora la ruta es self → … → destino

        if len(path) < 2:
            print(f"[{self.name}]  Ruta inválida: {path}")
            return

        # Calcular siguiente salto
        next_hop_name = path[1]
        next_hop = next((n for n in self.neighbors if n.name == next_hop_name), None)
        if not next_hop:
            print(f"[{self.name}]  No encuentro vecino {next_hop_name}")
            return

        msg_copy = message.copy_for_forward(self.name, next_hop.name)
        print(f"[{self.name}] ROUTE {message.to_node} → {next_hop.name} (ruta: {path})")
        next_hop._route(msg_copy)

    def _initialize_lsr(self):
        """Inicializa LSR: descubre vecinos y costos (sin flooding)"""
        print(f"[{self.name}]  Inicializando LSR...")
        
        # Simular costos a vecinos
        self.neighbor_costs.clear()  # Limpiar costos previos
        for neighbor in self.neighbors:
            self.neighbor_costs[neighbor.name] = 1
        
        print(f"[{self.name}] Vecinos detectados: {list(self.neighbor_costs.keys())}")

    def create_and_flood_lsp(self):
        """Crea LSP y hace flooding - versión corregida"""
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
        print(f"[{self.name}] Creando LSP: {lsp}")
        
        # Crear mensaje LSP para flooding
        lsp_message = Message(
            proto="lsr",
            mtype="lsp",
            from_node=self.name,
            to_node="broadcast",
            ttl=10,
            payload=lsp,
            msg_id=f"lsp_{self.name}_{self.sequence_number}"
        )
        
        # Flooding directo a vecinos
        print(f"[{self.name}] Iniciando flooding a {len(self.neighbors)} vecinos...")
        for neighbor in self.neighbors:
            print(f"[{self.name}] Enviando LSP → {neighbor.name}")
            neighbor.receive_lsp(lsp_message, from_neighbor=self.name)
        
        # Reconstruir nuestra topología
        self._rebuild_topology()

    def receive_lsp(self, lsp_message: Message, from_neighbor):
        """Recibe LSP de un vecino y lo procesa"""
        # Evitar loops
        if lsp_message.msg_id in self.received_msgs:
            return
        
        self.received_msgs.add(lsp_message.msg_id)
        lsp_data = lsp_message.payload
        sender_node = lsp_data["node"]
        
        # No procesar nuestro propio LSP
        if sender_node == self.name:
            return
        
        print(f"[{self.name}]  Recibido LSP de {sender_node} via {from_neighbor}")
        
        # Verificar si es más reciente
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
            print(f"[{self.name}]  Actualizando LSP de {sender_node}: {lsp_data['links']}")
            self.lsp_database[sender_node] = lsp_data
            self._rebuild_topology()
            
            # Propagar a otros vecinos (excepto de donde vino)
            lsp_message.ttl -= 1
            if lsp_message.ttl > 0:
                for neighbor in self.neighbors:
                    if neighbor.name != from_neighbor:
                        print(f"[{self.name}] Propagando LSP de {sender_node} → {neighbor.name}")
                        neighbor.receive_lsp(lsp_message, from_neighbor=self.name)

    def _rebuild_topology(self):
        """Reconstruye la topología completa desde los LSPs"""
        self.topology_graph = {}
        
        # Construir grafo desde todos los LSPs conocidos
        for node_name, lsp in self.lsp_database.items():
            self.topology_graph[node_name] = lsp["links"].copy()
        
        print(f"[{self.name}]  Topología reconstruida: {self.topology_graph}")
        
        # Ejecutar Dijkstra sobre la nueva topología
        if self.topology_graph:
            self._dijkstra_lsr()

    def _dijkstra_lsr(self):
        """Ejecuta Dijkstra sobre la topología construida por LSR"""
        dist = {n: float("inf") for n in self.topology_graph}
        prev = {n: None for n in self.topology_graph}
        
        # Asegurar que mi nodo esté en el grafo
        if self.name not in dist:
            dist[self.name] = float("inf")
            prev[self.name] = None
            
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
        print(f"[{self.name}]  LSR - Rutas calculadas: {self.prev}")

    def _route_lsr(self, message: Message):
        """Enrutamiento usando tabla calculada por LSR"""
        if message.to_node == self.name:
            print(f"[{self.name}]  RECIBÍ MENSAJE DESTINO: {message.payload}")
            return

        # Usar la tabla prev calculada por LSR
        if message.to_node not in self.prev:
            print(f"[{self.name}]  No hay ruta a {message.to_node}")
            return

        # Construir ruta completa
        path = []
        current = message.to_node
        while current != self.name:
            path.append(current)
            current = self.prev.get(current)
            if current is None:
                print(f"[{self.name}]  Ruta incompleta a {message.to_node}")
                return
        path.append(self.name)
        path.reverse()

        # Encontrar siguiente salto
        if len(path) < 2:
            print(f"[{self.name}]  Ruta muy corta: {path}")
            return
            
        next_hop_name = path[1]
        next_hop = next((n for n in self.neighbors if n.name == next_hop_name), None)
        
        if not next_hop:
            print(f"[{self.name}]  No encuentro vecino {next_hop_name}")
            return

        msg_copy = message.copy_for_forward(self.name, next_hop.name)
        print(f"[{self.name}] LSR ROUTE {message.to_node} → {next_hop.name} (ruta: {path})")
        next_hop.receive_message(msg_copy)

    def receive_message(self, message: Message):
        """Recibe mensaje según el protocolo"""
        try:
            if message.mtype == "message":
                if self.mode == "lsr":
                    self._route_lsr(message)
                elif self.mode == "flooding":
                    self._flood(message, incoming=message.from_node)
                elif self.mode == "dijkstra":
                    self._route(message)
            else:
                print(f"[{self.name}]  Tipo de mensaje desconocido: {message.mtype}")
        except Exception as e:
            print(f"[{self.name}]  Error procesando mensaje: {e}")
            
    def send_message(self, message: Message):
        """Envía mensaje según el modo"""
        # Asegurar que from_node esté correcto
        message.from_node = self.name
        
        if self.mode == "flooding":
            print(f"[{self.name}]  Enviando mensaje FLOOD: {message.payload}")
            self._flood(message, incoming=None)
        elif self.mode == "dijkstra":
            print(f"[{self.name}]  Enviando mensaje DIJKSTRA: {message.payload}")
            self._route(message)
        elif self.mode == "lsr":
            print(f"[{self.name}]  Enviando mensaje LSR: {message.payload}")
            self._route_lsr(message)

    def trigger_lsp_update(self):
        """Fuerza actualización de LSP"""
        if self.mode == "lsr":
            print(f"[{self.name}]  Forzando actualización de LSP...")
            self.create_and_flood_lsp()


# ============== EJEMPLO DE USO FUNCIONAL ==============
if __name__ == "__main__":
    print(" TESTING ALGORITMOS DE ENRUTAMIENTO")
    print("="*50)
    
    # ========== TEST LSR ==========
    print("\n TESTING LSR")
    
    # Crear nodos
    A = Node("A", mode="lsr")
    B = Node("B", mode="lsr")
    C = Node("C", mode="lsr")
    D = Node("D", mode="lsr")
    nodes = [A, B, C, D]

    # Conectar vecinos
    print(" Estableciendo conexiones...")
    A.add_neighbor(B)
    A.add_neighbor(C)
    B.add_neighbor(A)
    B.add_neighbor(D)
    C.add_neighbor(A)
    C.add_neighbor(D)
    D.add_neighbor(B)
    D.add_neighbor(C)

    # Inicializar LSR (solo detectar vecinos)
    print("\n Inicializando LSR...")
    for node in nodes:
        node._initialize_lsr()

    # Intercambio de LSPs
    print("\nIntercambiando LSPs...")
    for node in nodes:
        node.create_and_flood_lsp()

    # Mostrar estado final
    print(f"\n Estado final:")
    for node in nodes:
        lsps_known = list(node.lsp_database.keys())
        print(f"[{node.name}] LSPs conocidos: {lsps_known} | Rutas: {node.prev}")

    # Probar enrutamiento
    print(f"\n Probando enrutamiento A → D:")
    msg = Message(
        proto="lsr",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="¡Hola desde A usando LSR!"
    )
    A.send_message(msg)

    # ========== TEST FLOODING ==========
    print("\n" + "="*50)
    print(" TESTING FLOODING")
    
    A_flood = Node("A", mode="flooding")
    B_flood = Node("B", mode="flooding")
    C_flood = Node("C", mode="flooding")
    D_flood = Node("D", mode="flooding")

    A_flood.add_neighbor(B_flood)
    A_flood.add_neighbor(C_flood)
    B_flood.add_neighbor(A_flood)
    B_flood.add_neighbor(D_flood)
    C_flood.add_neighbor(A_flood)
    C_flood.add_neighbor(D_flood)
    D_flood.add_neighbor(B_flood)
    D_flood.add_neighbor(C_flood)

    msg_flood = Message(
        proto="flooding",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=5,
        payload="Hola desde A usando FLOODING!"
    )
    A_flood.send_message(msg_flood)

    # ========== TEST DIJKSTRA ==========
    print("\n" + "="*50)
    print(" TESTING DIJKSTRA")
    
    graph = {
        "A": {"B": 1, "C": 2},
        "B": {"A": 1, "D": 4},
        "C": {"A": 2, "D": 1},
        "D": {"B": 4, "C": 1}
    }
    
    A_dijk = Node("A", mode="dijkstra", graph=graph)
    B_dijk = Node("B", mode="dijkstra", graph=graph)
    C_dijk = Node("C", mode="dijkstra", graph=graph)
    D_dijk = Node("D", mode="dijkstra", graph=graph)

    A_dijk.add_neighbor(B_dijk)
    A_dijk.add_neighbor(C_dijk)
    B_dijk.add_neighbor(A_dijk)
    B_dijk.add_neighbor(D_dijk)
    C_dijk.add_neighbor(A_dijk)
    C_dijk.add_neighbor(D_dijk)
    D_dijk.add_neighbor(B_dijk)
    D_dijk.add_neighbor(C_dijk)

    msg_dijk = Message(
        proto="dijkstra",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="Hola desde A usando DIJKSTRA!"
    )
    A_dijk.send_message(msg_dijk)
    
    print("\n TODOS LOS TESTS COMPLETADOS")