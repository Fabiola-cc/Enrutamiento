# mata a nodos no vecinos segun timer
import asyncio
import copy
import traceback
import redis.asyncio as redis
import json
import heapq
import time
from typing import List, Dict, Optional
from collections import defaultdict

from modifiedMessage import Message

class Node:
    def __init__(
        self,

        # direccion de nuestro nodo
        name: str,

        # informacion de topología
        neighbors: Optional[Dict[str, int]] = None,  # dict vecino:coste
        mode: str = "flooding",
        graph: Optional[Dict[str, Dict[str, int]]] = None
    ):
        self.name = name

        # vecinos directos con costos
        self.neighbor_costs: Dict[str, int] = neighbors or {}
        self.neighbors = list(self.neighbor_costs.keys())  # lista de nombres de vecinos

        # para control de flooding
        self.received_msgs = set()              

        # modo de enrutamiento
        self.mode = mode  

        self.graph = graph                      
        
        # Internal topology table: {source: {destination: {"weight": int, "time": int}}}
        # Solo el nodo propio tiene timers para vecinos directos
        self.topology_table = defaultdict(lambda: defaultdict(dict)) # Esta inicializacion permite que las 'llaves' se creen automáticamente
        
        # Initialize our own entry in topology table
        self.topology_table[self.name] = {}
        for neighbor, weight in self.neighbor_costs.items():
            self.topology_table[self.name][neighbor] = {
                "weight": weight,
                "time": 10  # Timer inicial de 10 segundos para vecinos directos
            }

        # Cliente Redis (async)
        self.r = redis.Redis(
            host='homelab.fortiguate.com',
            port=16379,
            password='4YNydkHFPcayvlx7$zpKm',
            decode_responses=True
        )

    #  INICIO DEL PROCESO
    async def start(self):
        """Suscribe al canal y procesa mensajes (bloqueante)."""
        async with self.r.pubsub() as pubsub:
            await pubsub.subscribe(self.name)
            print(f"[{self.name}] Suscrito a {self.name}")

            # Suscribirse a neighbors para debugging
            for neighbor in self.neighbors:
                await pubsub.subscribe(neighbor)
                print(f"[{self.name}] Suscrito a {neighbor}")

            while True:
                # get_message con timeout corto evita bloqueo indefinido
                raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if raw is None:
                    await asyncio.sleep(0.1)  # yield
                    continue
                try:
                    data = raw["data"]
                    # Si pub/sub entrega strings, aseguramos parseo correcto
                    if isinstance(data, str):
                        msg_obj = Message.from_json(data)
                    else:
                        # decode si necesita
                        msg_obj = Message.from_json(data.decode() if isinstance(data, bytes) else str(data))
                    await self.receive_message(msg_obj)
                except Exception as e:
                    print(f"[{self.name}]  Error parseando mensaje: {e}")

    # PUBLICADOR A REDIS
    async def publish(self, msg: Message, goesTo: str = None) -> int:
        """Publica (async) en el canal nodo:<to_node>. Devuelve número de subscriptores."""
        target = goesTo if goesTo is not None else msg.to_node

        receivers = await self.r.publish(target, msg.to_json())
        if(msg.mtype == "hello"):
            print(f"[{self.name}] {msg.mtype} → {msg.to_node}: (subs: {receivers})")
        return receivers
    
    # ALGORITMOS DE ENRUTAMIENTO
    # flooding
    async def _flood(self, msg: Message):
        """Flooding: reenvía a todos los vecinos excepto 'incoming'."""

        # Reenviar a cada vecino excepto de donde vino
        for neighbor in self.neighbors:
            if neighbor == msg.from_node:
                continue
            msg_copy = msg.copy_for_forward(neighbor)
            await self.publish(msg_copy, neighbor)
    
    # Dijkstra cálculo
    def _dijkstra(self):
        """Calcula distancias mínimas y prev para backtracking sobre self.graph."""
        if not self.graph:
            self.build_graph_from_topology()
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
                if dist.get(v, float("inf")) > d + w:
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        self.prev = prev
        print(f"[{self.name}] Distancias calculadas (prev): {self.prev}")

    # Dijkstra envío
    async def _route(self, msg: Message):
        """Enrutamiento usando tabla `self.prev` (Dijkstra sobre graph)."""
        path = []
        current = msg.to_node
        while current != self.name:
            path.append(current)
            current = self.prev.get(current)
            if current is None:
                print(f"[{self.name}]  No hay ruta completa a {msg.to_node}")
                return
        path.append(self.name)
        path.reverse()

        # Siguiente salto
        if len(path) < 2:
            print(f"[{self.name}]  Ruta trivial/incorrecta: {path}")
            return
        next_hop = path[1]

        msg_copy = msg.copy_for_forward(self.name, next_hop)
        print(f"[{self.name}] ROUTE {msg.to_node} → {next_hop} (ruta: {path})")
        await self.publish(msg_copy)

    # ENVIO Y RECEPCION DE MENSAJES
    async def receive_message(self, msg: Message):
        """Procesa mensaje entrante y lo despacha al algoritmo correspondiente (async)."""        
        if(msg.from_node == self.name):
            return

        try:
            # señales recurrentes
            if msg.mtype == "hello":
                if(neighbors.__contains__(msg.from_node)):
                    self.topology_table[self.name][msg.from_node]["time"] = 10 # RESET TIMER
                    print(f"Hello BIEN recibido de {msg.from_node}") #DEBUG
                else:
                    print(f"Hello EXTRAÑO recibido de {msg.from_node}") #DEBUG
                return

            # actualizar info
            elif msg.mtype == "message":
                
                if msg.to_node not in self.topology_table:
                    self.topology_table[msg.to_node] = {}
                if msg.from_node not in self.topology_table[msg.to_node]:
                    self.topology_table[msg.to_node][msg.from_node] = {
                        "weight": msg.hops,  # acá usas hops como peso inicial
                        "time": 15
                    }
                    print(f"Message recibido de {msg.from_node} para {msg.to_node}") #DEBUG

                previous_weight = self.topology_table[msg.to_node][msg.from_node]["weight"]

                if(previous_weight!=msg.hops): # Cambiar y Mandar solamente información nueva
                    self.topology_table[msg.to_node][msg.from_node]["weight"] = msg.hops # update from propagation
                    self.topology_table[msg.to_node][msg.from_node]["time"] = 15 # RESET TIMER
                return
            else:
                print(f"[{self.name}] de {msg.from_node}  Tipo de mensaje desconocido: {msg.mtype}")
        except Exception as e:
            print(f"[{self.name}]  Error procesando mensaje: {e}")
            traceback.print_exc()   # imprime el stack completo
            

    async def update_neighbors(self, interval: int = 3):
        """Envia HELLOs periódicamente cada 3 segundos"""
        while True:
            await asyncio.sleep(interval)
            # Mandar messages con pesos a nuestros vecinos
            # Hacer copia profunda de la topología
            topology_copy = copy.deepcopy(self.topology_table)

            for source, neighbors in topology_copy.items():
                for destination, data in neighbors.items():
                    weight = data.get("weight")
                    msg = Message(
                        type="message",
                        from_node=source,       # quién anuncia
                        to_node=destination,    # hacia quién tiene conexión
                        hops=weight             # el costo del enlace
                    )
                    await self._flood(msg)

            for neighbor in self.neighbors: # crea un mensaje por vecino
                hello_msg = Message(
                    type="hello",
                    from_node=self.name,
                    to_node=neighbor,
                    hops=node.neighbor_costs.get(neighbor)
                )
                await self.publish(hello_msg) # mandar un hello a cada vecino
            
            print("ENVIADOS hello y message") #DEBUG

    # ACTUALIZACION DE TOPOLOGÍA
    async def maintain_topology(self, interval: int = 1):
        """
        Mantiene la topología: decrementa timers y elimina vecinos/enlaces muertos.
        
        Args:
            interval (int): cada cuántos segundos revisar (default 1s).
        """
        while True:
            try:
                # Revisar timer de MIS vecinos
                for neighbor in list(self.topology_table[self.name].keys()):
                    entry = self.topology_table[self.name][neighbor]
                    entry["time"] -= 1

                    # Eliminar nodo muerto
                    if entry["time"] <= 0:
                        print(f"[{self.name}] Eliminando enlace a {neighbor} por timeout") # DEBUG
                        del self.topology_table[self.name][neighbor]
                        self.neighbors.remove(neighbor)
                        del self.neighbor_costs[neighbor]

                # Recorremos una copia de llaves porque vamos a borrar
                for node in list(self.topology_table.keys()):
                    if (node == self.name):
                        continue

                    for neighbor in list(self.topology_table[node].keys()):
                        entry = self.topology_table[node][neighbor]

                        if "time" in entry:
                            entry["time"] -= interval

                            if entry["time"] <= 0:
                                print(f"[{self.name}] Eliminando enlace {node} ↔ {neighbor} por timeout") # DEBUG
                                del self.topology_table[node][neighbor]

                                # si ese nodo se quedó sin vecinos, borrarlo también
                                if not self.topology_table[node]:
                                    del self.topology_table[node]

            except Exception as e:
                print(f"[{self.name}] Error en maintain_topology: {e}")

            await asyncio.sleep(interval)

    # USO DE DIJKSTRA
    def build_graph_from_topology(self):
        """Construye el grafo {u: {v: weight}} a partir de topology_table,
        ignorando enlaces expirados (time <= 0)."""
        graph = {}
        for src, neighbors in self.topology_table.items():
            graph[src] = {}
            for dst, data in neighbors.items():
                if data.get("time", 0) > 0:  # solo enlaces vivos
                    graph[src][dst] = data["weight"]
        return graph

    async def console_input(self):
        """Interfaz de usuario en consola para cambiar modos"""
        loop = asyncio.get_event_loop()
        while True:
            user_input = await loop.run_in_executor(None, input, f"[{self.name}] > ")
            parts = user_input.strip().split(" ", 2)

            if not parts:
                continue
            cmd = parts[0].lower()

            # --------- SALIR ---------
            if cmd == "exit":
                print(f"[{self.name}] Terminando...")
                break

            # --------- CAMBIO DE MODO ---------
            elif cmd == "mode":
                if len(parts) < 2:
                    print("Uso: mode <flooding|dijkstra>")
                    continue
                new_mode = parts[1].lower()
                if new_mode not in ("flooding",  "dijkstra"):
                    print("Modo inválido. Usa flooding o dijkstra.")
                    continue
                self.mode = new_mode
                print(f"[{self.name}] Modo cambiado a {new_mode}") #DEBUG
                if new_mode == "dijkstra":
                    await self._dijkstra()

def load_graph_from_file(path="topologia.txt"):
    graph = {}
    with open(path) as f:
        content = f.read().strip()
        edges = content.split(",")
        for edge in edges:
            edge = edge.strip()
            if not edge:
                continue
            # Ejemplo: "N1-N2:20"
            try:
                nodes, cost = edge.split(":")
                u, v = nodes.split("-")
                u = u.replace("N", "")
                v = v.replace("N", "")
                u = f"sec30.grupo{u}.nodo{u}"
                v = f"sec30.grupo{v}.nodo{v}"
                w = int(cost)

                # Grafo no dirigido
                graph.setdefault(u, {})[v] = w
                graph.setdefault(v, {})[u] = w
            except Exception as e:
                print(f"Error parsing edge '{edge}': {e}")
    return graph

#  CLI PARA LANZAR UN NODO EN SU PROPIO PROCESO 
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python node_redis.py <NAME> [vecino:coste ...]")
        sys.exit(1)

    groupNum = sys.argv[1]
    name = f"sec30.grupo{groupNum}.nodo{groupNum}"
    neighbors = {}
    
    # Buscar argumento opcional de topología
    if "--topo" in sys.argv:
        topo_index = sys.argv.index("--topo")
        topo_file = sys.argv[topo_index + 1]
        graph = load_graph_from_file(topo_file)
    else: # topología default
        graph = load_graph_from_file()
    # extraer vecinos directos desde el grafo
    if name in graph:
        for n in graph[name].keys():
            neighbors[n] = graph[name][n]

    # Crear nodo
    node = Node(name, neighbors, mode="flooding", graph=graph)

    print(f"[{name}] Iniciando nodo con Redis Async...")
    print(f"[{name}] Vecinos configurados: {neighbors}")
    print(f"[{name}] Modo: {node.mode}")

    async def main():
        try:
            await asyncio.gather(
                node.start(), # iniciar conexión 
                node.update_neighbors(), # mandar señal de vida, cada 3s
                node.maintain_topology() # revisar vida de cada nodo, cada 1s
            )
        except KeyboardInterrupt:
            print(f"\n[{name}] Terminando...")

    asyncio.run(main())
