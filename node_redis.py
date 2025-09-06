# node_redis.py
import asyncio
import redis.asyncio as redis
import json
import heapq
import time
from typing import List, Dict, Optional

from MessageStruct import Message

class Node:
    def __init__(
        self,
        name: str,
        neighbors: Optional[List[str]] = None,
        mode: str = "flooding",
        graph: Optional[Dict[str, Dict[str, int]]] = None,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None
    ):
        self.name = name
        self.neighbors = neighbors or []        # lista de nombres de vecinos (strings)
        self.received_msgs = set()              # IDs de mensajes ya recibidos

        self.mode = mode                        # "flooding" | "dijkstra" | "lsr"
        self.graph = graph or {}                # topología completa para Dijkstra (si aplica)
        self.prev = {}                          # prev para backtracking (dijkstra)
        self.lsp_database: Dict[str, dict] = {} # LSPs conocidos
        self.sequence_number = 0
        self.neighbor_costs: Dict[str,int] = {} # coste a vecinos directos
        self.topology_graph: Dict[str, Dict[str,int]] = {}

        # Cliente Redis (async)
        self.r = redis.Redis(host=host, port=port, password=password, decode_responses=True)

        # No inicializamos LSR/Dijkstra automáticamente (necesita event loop).
        # Si deseas inicializar Dijkstra desde start(), llama a node._dijkstra() manualmente.

    #  Dijkstra (local sobre `graph`) 
    def _dijkstra(self):
        """Calcula distancias mínimas y prev para backtracking sobre self.graph."""
        dist = {n: float("inf") for n in self.graph}
        prev = {n: None for n in self.graph}
        if self.name not in dist:
            # Asegurar que el nodo figure en el grafo si no está
            dist[self.name] = 0
            prev[self.name] = None
        else:
            dist[self.name] = 0

        pq = [(0, self.name)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, w in self.graph.get(u, {}).items():
                if dist.get(v, float("inf")) > d + w:
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        self.prev = prev
        print(f"[{self.name}] Distancias calculadas (prev): {self.prev}")

    #  Publicador a Redis 
    async def publish(self, message: Message) -> int:
        """Publica (async) en el canal nodo:<to_node>. Devuelve número de subscriptores."""
        channel = f"nodo:{message.to_node}"
        # opcional: registrar hora de envío
        message.headers["sent_at"] = time.time()
        receivers = await self.r.publish(channel, message.to_json())
        print(f"[{self.name}] → {message.to_node}: {message.payload} (subs: {receivers})")
        return receivers

    #  Flooding general (async) 
    async def _flood(self, message: Message, incoming: Optional[str]):
        """Flooding: reenvía a todos los vecinos excepto 'incoming'."""
        if message.ttl <= 0:
            return
        if message.msg_id in self.received_msgs:
            return

        self.received_msgs.add(message.msg_id)

        if message.to_node == self.name:
            print(f"[{self.name}] Recibí mensaje DESTINO: {message.payload}")
            # NOTA: en flooding puedes decidir si procesas y **no** reenvías o procesas y reenvías.
            # Aquí procesamos y aún permitimos reenvío según ttl.

        # Decrementar TTL (hacemos copia antes de publicar)
        message.ttl -= 1

        # Reenviar a cada vecino excepto de donde vino
        for neighbor in self.neighbors:
            if neighbor == incoming:
                continue
            msg_copy = message.copy_for_forward(self.name, neighbor)
            print(f"[{self.name}] FLOOD → {neighbor}")
            await self.publish(msg_copy)

    #  Routing (Dijkstra) 
    async def _route(self, message: Message):
        """Enrutamiento usando tabla `self.prev` (Dijkstra sobre graph)."""
        if message.to_node == self.name:
            print(f"[{self.name}] Recibí mensaje DESTINO: {message.payload}")
            return

        # Reconstruir ruta backtracking desde destino hasta self
        path = []
        current = message.to_node
        # Si no conocemos prev para ese destino, no hay ruta
        if current not in self.prev:
            print(f"[{self.name}] No hay ruta a {message.to_node}")
            return

        while current != self.name:
            path.append(current)
            current = self.prev.get(current)
            if current is None:
                print(f"[{self.name}] No hay ruta completa a {message.to_node}")
                return
        path.append(self.name)
        path.reverse()

        # Siguiente salto
        if len(path) < 2:
            print(f"[{self.name}] Ruta trivial/incorrecta: {path}")
            return
        next_hop = path[1]

        msg_copy = message.copy_for_forward(self.name, next_hop)
        print(f"[{self.name}] ROUTE {message.to_node} → {next_hop} (ruta: {path})")
        await self.publish(msg_copy)

    #  LSR (LSP handling) 
    def _initialize_lsr(self):
        """Inicialización sin I/O. Prepara neighbor_costs y crea primer LSP vía trigger."""
        print(f"[{self.name}] Inicializando LSR (local data)...")
        for neighbor in self.neighbors:
            self.neighbor_costs[neighbor] = 1  # valor por defecto

    async def _create_and_flood_lsp(self):
        """Crea LSP y lo propaga (async)."""
        self.sequence_number += 1
        lsp = {
            "node": self.name,
            "sequence": self.sequence_number,
            "timestamp": time.time(),
            "links": self.neighbor_costs.copy()
        }
        self.lsp_database[self.name] = lsp

        lsp_message = Message(
            proto="lsr",
            mtype="lsp",
            from_node=self.name,
            to_node="broadcast",   # semántica interna
            ttl=10,
            payload=lsp,
            msg_id=f"lsp_{self.name}_{self.sequence_number}"
        )
        print(f"[{self.name}] Creando LSP: {lsp}")
        # Propagar LSP igual que flooding pero con la lógica de actualización
        await self._flood_lsp(lsp_message, incoming=None)
        # luego reconstruir topología local
        self._rebuild_topology()

    async def _flood_lsp(self, lsp_message: Message, incoming: Optional[str]):
        """Propaga LSP a vecinos (async). Actualiza lsp_database si es necesario."""
        if lsp_message.msg_id in self.received_msgs:
            return

        self.received_msgs.add(lsp_message.msg_id)
        lsp_data = lsp_message.payload
        sender_node = lsp_data["node"]

        # decide si actualizar
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
            print(f"[{self.name}] Recibido/Actualizado LSP de {sender_node}: {lsp_data['links']}")
            self.lsp_database[sender_node] = lsp_data
            self._rebuild_topology()

            # continuar flooding si ttl>0
            lsp_message.ttl -= 1
            if lsp_message.ttl > 0:
                for neighbor in self.neighbors:
                    if neighbor == incoming:
                        continue
                    msg_copy = lsp_message.copy_for_forward(self.name, neighbor)
                    print(f"[{self.name}] Propagando LSP → {neighbor}")
                    await self.publish(msg_copy)

    def _rebuild_topology(self):
        """Construye topología a partir de LSPs conocidas y calcula rutas LSR (dijkstra)."""
        self.topology_graph = {}
        for node_name, lsp in self.lsp_database.items():
            self.topology_graph[node_name] = lsp["links"].copy()
        print(f"[{self.name}] Topología reconstruida: {self.topology_graph}")
        if self.topology_graph:
            self._dijkstra_lsr()

    def _dijkstra_lsr(self):
        """Corre Dijkstra sobre topology_graph y llena self.prev."""
        dist = {n: float("inf") for n in self.topology_graph}
        prev = {n: None for n in self.topology_graph}
        if self.name not in dist:
            dist[self.name] = 0
            prev[self.name] = None
        else:
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

    async def _route_lsr(self, message: Message):
        """Enrutamiento usando tabla resultante de LSR (async)."""
        if message.to_node == self.name:
            print(f"[{self.name}] RECIBÍ mensaje DESTINO: {message.payload}")
            return
        if message.to_node not in self.prev:
            print(f"[{self.name}] No hay ruta a {message.to_node}")
            return

        path = []
        current = message.to_node
        while current != self.name:
            path.append(current)
            current = self.prev.get(current)
            if current is None:
                print(f"[{self.name}] Ruta incompleta a {message.to_node}")
                return
        path.append(self.name)
        path.reverse()

        next_hop = path[1]
        msg_copy = message.copy_for_forward(self.name, next_hop)
        print(f"[{self.name}] LSR ROUTE {message.to_node} → {next_hop} (ruta: {path})")
        await self.publish(msg_copy)

    #  Start / Receive 
    async def start(self):
        """Suscribe al canal y procesa mensajes (bloqueante)."""
        async with self.r.pubsub() as pubsub:
            await pubsub.subscribe(f"nodo:{self.name}")
            print(f"[{self.name}] Suscrito a nodo:{self.name}")

            while True:
                # get_message con timeout corto evita bloqueo indefinido si deseas hacer otras tareas
                raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if raw is None:
                    await asyncio.sleep(0)  # yield
                    continue
                try:
                    data = raw["data"]
                    # Si pub/sub entrega strings, aseguramos parseo correcto
                    if isinstance(data, str):
                        msg_obj = Message.from_json(data)
                    else:
                        # decode si necesita
                        msg_obj = Message.from_json(json.dumps(data))
                    await self.receive_message(msg_obj)
                except Exception as e:
                    print(f"[{self.name}] Error parseando mensaje: {e}")

    async def receive_message(self, message: Message):
        """Procesa mensaje entrante y lo despacha al algoritmo correspondiente (async)."""
        if message.msg_id in self.received_msgs:
            return
        # NOTA: muchas rutinas (p.ej. _flood_lsp) también marcan recibido; marcamos temprano para evitar dups
        self.received_msgs.add(message.msg_id)

        print(f"[{self.name}] Recibido de {message.from_node}: {message.payload}")

        try:
            if message.mtype == "lsp":
                # lsp flooding tiene su propia lógica (async)
                await self._flood_lsp(message, incoming=message.from_node)
            elif message.mtype == "message":
                if self.mode == "lsr":
                    await self._route_lsr(message)
                elif self.mode == "flooding":
                    await self._flood(message, incoming=message.from_node)
                elif self.mode == "dijkstra":
                    await self._route(message)
                else:
                    print(f"[{self.name}] Modo desconocido: {self.mode}")
            else:
                print(f"[{self.name}] Tipo de mensaje desconocido: {message.mtype}")
        except Exception as e:
            print(f"[{self.name}] Error procesando mensaje: {e}")

    #  Interface pública 
    async def send_message(self, message: Message):
        """Enviar mensaje inicial según el modo (async)."""
        # aseguramos que message.from_node refleje el origin actual
        message.from_node = self.name

        if self.mode == "flooding":
            # iniciar flooding desde este nodo
            print(f"[{self.name}] Enviando mensaje FLOOD: {message.payload}")
            await self._flood(message, incoming=None)
        elif self.mode == "dijkstra":
            print(f"[{self.name}] Enviando mensaje DIJKSTRA: {message.payload}")
            await self._route(message)
        elif self.mode == "lsr":
            print(f"[{self.name}] Enviando mensaje LSR: {message.payload}")
            await self._route_lsr(message)
        else:
            # como fallback, publicarlo al primer vecino
            if self.neighbors:
                target = self.neighbors[0]
                msg_copy = message.copy_for_forward(self.name, target)
                await self.publish(msg_copy)
            else:
                print(f"[{self.name}] No neighbors to send to.")

    async def trigger_lsp_update(self):
        """Fuerza creación y flood de LSP (async)."""
        if self.mode != "lsr":
            print(f"[{self.name}] trigger_lsp_update ignorado (no en modo lsr).")
            return
        # asegurar neighbor_costs actualizado
        for n in self.neighbors:
            self.neighbor_costs.setdefault(n, 1)
        await self._create_and_flood_lsp()


#  CLI para lanzar un nodo en su propio proceso 
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python node_redis.py <NAME> [neighbor1 neighbor2 ...]")
        sys.exit(1)

    name = sys.argv[1]
    neighbors = sys.argv[2:]
    node = Node(name, neighbors)

    # Ejemplo: arrancar nodo en modo flooding; para lsr/dijkstra cambia node.mode y/o node.graph antes de start
    try:
        asyncio.run(node.start())
    except KeyboardInterrupt:
        print(f"[{name}] Terminando...")