# node_redis.py - Version corregida
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
        neighbors: Optional[Dict[str, int]] = None,  # ahora dict vecino:coste
        mode: str = "flooding",
        graph: Optional[Dict[str, Dict[str, int]]] = None,
        host: str = "homelab.fortiguate.com",
        port: int = 16379,
        password: Optional[str] = "4YNydkHFPcayvlx7$zpKm"
    ):
        self.name = name

        # vecinos directos con costos
        self.neighbor_costs: Dict[str, int] = neighbors or {}
        self.neighbors = list(self.neighbor_costs.keys())  # lista de nombres de vecinos

        # para control de flooding
        self.received_msgs = set()              

        # modo de enrutamiento
        self.mode = mode                        
        self.graph = graph or {}                # topología completa (solo si usas Dijkstra global)
        self.prev = {}                          # prev para backtracking (Dijkstra)
        self.lsp_database: Dict[str, dict] = {} # base de datos de LSPs conocidos
        self.sequence_number = 0
        self.topology_graph: Dict[str, Dict[str, int]] = {}  # grafo reconstruido en LSR

        # Cliente Redis (async)
        self.r = redis.Redis(
            host=host, 
            port=port, 
            password=password, 
            decode_responses=True
        )

        # Solo inicializar Dijkstra automáticamente si tiene grafo
        if self.mode == "dijkstra" and self.graph:
            self._dijkstra()


    # ========== DIJKSTRA (local sobre `graph`) ==========
    def _dijkstra(self):
        """Calcula distancias mínimas y prev para backtracking sobre self.graph."""
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
                if dist.get(v, float("inf")) > d + w:
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        self.prev = prev
        print(f"[{self.name}] Distancias calculadas (prev): {self.prev}")

    # ========== PUBLICADOR A REDIS ==========
    async def publish(self, message: Message) -> int:
        """Publica (async) en el canal nodo:<to_node>. Devuelve número de subscriptores."""
        channel = f"nodo:{message.to_node}"
        # opcional: registrar hora de envío
        message.headers["sent_at"] = time.time()
        receivers = await self.r.publish(channel, message.to_json())
        print(f"[{self.name}] → {message.to_node}: {message.payload} (subs: {receivers})")
        return receivers

    # ========== FLOODING GENERAL (async) ==========
    async def _flood(self, message: Message, incoming: Optional[str]):
        """Flooding: reenvía a todos los vecinos excepto 'incoming'."""
        if message.ttl <= 0:
            return
        if message.msg_id in self.received_msgs:
            return

        self.received_msgs.add(message.msg_id)

        if message.to_node == self.name:
            print(f"[{self.name}]  RECIBÍ MENSAJE DESTINO: {message.payload}")
            return

        # Decrementar TTL (hacemos copia antes de publicar)
        message.ttl -= 1

        # Reenviar a cada vecino excepto de donde vino
        for neighbor in self.neighbors:
            if neighbor == incoming:
                continue
            msg_copy = message.copy_for_forward(self.name, neighbor)
            print(f"[{self.name}] FLOOD → {neighbor}")
            await self.publish(msg_copy)

    # ========== ROUTING (Dijkstra) ==========
    async def _route(self, message: Message):
        """Enrutamiento usando tabla `self.prev` (Dijkstra sobre graph)."""
        if message.to_node == self.name:
            print(f"[{self.name}]  RECIBÍ MENSAJE DESTINO: {message.payload}")
            return

        # Reconstruir ruta backtracking desde destino hasta self
        if message.to_node not in self.prev:
            print(f"[{self.name}]  No hay ruta a {message.to_node}")
            return

        path = []
        current = message.to_node
        while current != self.name:
            path.append(current)
            current = self.prev.get(current)
            if current is None:
                print(f"[{self.name}]  No hay ruta completa a {message.to_node}")
                return
        path.append(self.name)
        path.reverse()

        # Siguiente salto
        if len(path) < 2:
            print(f"[{self.name}]  Ruta trivial/incorrecta: {path}")
            return
        next_hop = path[1]

        msg_copy = message.copy_for_forward(self.name, next_hop)
        print(f"[{self.name}] ROUTE {message.to_node} → {next_hop} (ruta: {path})")
        await self.publish(msg_copy)

    # ========== LSR METHODS - CORREGIDOS ==========
    def _initialize_lsr(self):
        """Inicialización sin I/O. Prepara neighbor_costs y detecta vecinos."""
        print(f"[{self.name}]  Inicializando LSR (local data)...")
        
        # Limpiar datos previos
        self.neighbor_costs.clear()
        
        # Detectar vecinos directos y asignar costos
        for neighbor in self.neighbors:
            self.neighbor_costs[neighbor] = 1  # valor por defecto

        print(f"[{self.name}] Vecinos detectados: {list(self.neighbor_costs.keys())}")

    async def create_and_flood_lsp(self):
        """Crea LSP y lo propaga (async) - VERSIÓN CORREGIDA."""
        self.sequence_number += 1
        lsp = {
            "node": self.name,
            "sequence": self.sequence_number,
            "timestamp": time.time(),
            "links": self.neighbor_costs.copy()
        }
        self.lsp_database[self.name] = lsp

        # Crear mensaje LSP
        lsp_message = Message(
            proto="lsr",
            type="lsp",
            from_node=self.name,
            to_node="broadcast",   # semántica interna
            ttl=10,
            payload=lsp,
            msg_id=f"lsp_{self.name}_{self.sequence_number}"
        )

        # Flooding directo a vecinos (como en Node.py)
        for neighbor in self.neighbors:
            # En Redis, publicamos directamente al canal del vecino
            await self.publish_lsp_to_neighbor(lsp_message, neighbor)
        
        # Reconstruir topología local
        self._rebuild_topology()

    async def publish_lsp_to_neighbor(self, lsp_message: Message, neighbor: str):
        """Publica LSP directamente al canal de un vecino específico"""
        channel = f"nodo:{neighbor}"
        await self.r.publish(channel, lsp_message.to_json())

    async def receive_lsp(self, lsp_message: Message, from_neighbor: str):
        """Recibe LSP de un vecino y lo procesa (async)."""
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
                    if neighbor != from_neighbor:
                        print(f"[{self.name}]  Propagando LSP de {sender_node} → {neighbor}")
                        await self.publish_lsp_to_neighbor(lsp_message, neighbor)

    def _rebuild_topology(self):
        """Construye topología a partir de LSPs conocidas y calcula rutas LSR (dijkstra)."""
        self.topology_graph = {}
        for node_name, lsp in self.lsp_database.items():
            self.topology_graph[node_name] = lsp["links"].copy()
        if self.topology_graph:
            self._dijkstra_lsr()

    def _dijkstra_lsr(self):
        """Corre Dijkstra sobre topology_graph y llena self.prev."""
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

    async def _route_lsr(self, message: Message):
        """Enrutamiento usando tabla resultante de LSR (async)."""
        if message.to_node == self.name:
            print(f"[{self.name}]  RECIBÍ MENSAJE DESTINO: {message.payload}")
            return
        if message.to_node not in self.prev:
            print(f"[{self.name}]  No hay ruta a {message.to_node}")
            return

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

        if len(path) < 2:
            print(f"[{self.name}]  Ruta muy corta: {path}")
            return

        next_hop = path[1]
        msg_copy = message.copy_for_forward(self.name, next_hop)
        print(f"[{self.name}] LSR ROUTE {message.to_node} → {next_hop} (ruta: {path})")
        await self.publish(msg_copy)

    # ========== START / RECEIVE ==========
    async def start(self):
        """Suscribe al canal y procesa mensajes (bloqueante)."""
        async with self.r.pubsub() as pubsub:
            await pubsub.subscribe(f"nodo:{self.name}")
            print(f"[{self.name}] Suscrito a nodo:{self.name}")

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

    async def receive_message(self, message: Message):
        """Procesa mensaje entrante y lo despacha al algoritmo correspondiente (async)."""
        print(f"[{self.name}]  Recibido de {message.from_node}: {message.mtype} - {message.payload}")

        # --- MANEJO DE PING / PONG ---
        if message.mtype == "ping":
            # Responder automáticamente con pong
            pong_msg = Message(
                proto="control",   # no va por algoritmo
                type="pong",
                from_node=self.name,
                to_node=message.from_node,
                ttl=1,
                payload={"timestamp": message.payload["timestamp"]}
            )
            await self.publish(pong_msg)
            return

        elif message.mtype == "pong":
            # solo se maneja en send_ping, no necesita algoritmo
            return

        # --- MENSAJES NORMALES ---
        try:
            if message.mtype == "lsp":
                await self.receive_lsp(message, from_neighbor=message.from_node)
            elif message.mtype == "message":
                if self.mode == "lsr":
                    await self._route_lsr(message)
                elif self.mode == "flooding":
                    await self._flood(message, incoming=message.from_node)
                elif self.mode == "dijkstra":
                    await self._route(message)
                else:
                    print(f"[{self.name}]  Modo desconocido: {self.mode}")
            else:
                print(f"[{self.name}]  Tipo de mensaje desconocido: {message.mtype}")
        except Exception as e:
            print(f"[{self.name}]  Error procesando mensaje: {e}")


    # ========== INTERFACE PÚBLICA ==========
    async def send_message(self, message: Message):
        """Enviar mensaje inicial según el modo (async)."""
        # aseguramos que message.from_node refleje el origin actual
        message.from_node = self.name

        if self.mode == "flooding":
            print(f"[{self.name}]  Enviando mensaje FLOOD: {message.payload}")
            await self._flood(message, incoming=None)
        elif self.mode == "dijkstra":
            print(f"[{self.name}]  Enviando mensaje DIJKSTRA: {message.payload}")
            await self._route(message)
        elif self.mode == "lsr":
            print(f"[{self.name}]  Enviando mensaje LSR: {message.payload}")
            await self._route_lsr(message)
        else:
            print(f"[{self.name}]  Modo desconocido: {self.mode}")

    async def send_ping(self, to_node: str, timeout: float = 2.0):
        timestamp = time.time()
        ping_msg = Message(
            proto=self.mode,
            type="ping",
            from_node=self.name,
            to_node=to_node,
            ttl=1,
            payload={"timestamp": timestamp}
        )

        # Crear future para esperar pong
        fut = asyncio.get_event_loop().create_future()

        async def pong_listener(msg: Message):
            if msg.mtype == "pong" and msg.from_node == to_node and msg.to_node == self.name:
                rtt = time.time() - msg.payload["timestamp"]
                print(f"[{self.name}] Ping {self.name} → {to_node}: {rtt:.3f} s")
                if not fut.done():
                    fut.set_result(True)

        # Suscribirse temporalmente a nuestro canal para escuchar pong
        async with self.r.pubsub() as pubsub:
            await pubsub.subscribe(f"nodo:{self.name}")
            await self.publish(ping_msg)  # enviar ping
            start = time.time()
            while True:
                raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if raw:
                    data = raw["data"]
                    if isinstance(data, str):
                        msg_obj = Message.from_json(data)
                    else:
                        msg_obj = Message.from_json(data.decode() if isinstance(data, bytes) else str(data))
                    await pong_listener(msg_obj)
                if fut.done():
                    break
                if time.time() - start > timeout:
                    if not fut.done():
                        print(f"[{self.name}] Ping {self.name} → {to_node}: TIMEOUT")
                        fut.set_result(False)
                    break
                await asyncio.sleep(0.05)


    async def trigger_lsp_update(self):
        """Fuerza creación y flood de LSP (async)."""
        if self.mode != "lsr":
            print(f"[{self.name}] trigger_lsp_update ignorado (no en modo lsr).")
            return
        # asegurar neighbor_costs actualizado
        for n in self.neighbors:
            self.neighbor_costs.setdefault(n, 1)
        await self.create_and_flood_lsp()

    # ========== MÉTODOS DE CONVENIENCIA PARA LSR ==========
    async def initialize_lsr_and_flood(self):
        """Inicializa LSR y hace flooding inicial de LSPs"""
        if self.mode != "lsr":
            return
        self._initialize_lsr()
        await self.create_and_flood_lsp()

    async def console_input(self):
        """Interfaz de usuario en consola para enviar mensajes y cambiar modos"""
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
                    print("Uso: mode <flooding|lsr|dijkstra>")
                    continue
                new_mode = parts[1].lower()
                if new_mode not in ("flooding", "lsr", "dijkstra"):
                    print("Modo inválido. Usa flooding, lsr o dijkstra.")
                    continue
                self.mode = new_mode
                print(f"[{self.name}] Modo cambiado a {new_mode}")
                if new_mode == "lsr":
                    await self.initialize_lsr_and_flood()

            # --------- ENVÍO DE MENSAJES ---------
            elif cmd == "send":
                if len(parts) < 3:
                    print("Uso: send <destino> <mensaje>")
                    continue
                to_node, payload = parts[1], parts[2]
                msg = Message(
                    proto=self.mode,
                    type="message",
                    from_node=self.name,
                    to_node=to_node,
                    ttl=10,
                    payload=payload
                )
                await self.send_message(msg)

            # --------- PING / HELLO ---------
            elif cmd == "ping":
                if len(parts) < 2:
                    print("Uso: ping <destino>")
                    continue
                to_node = parts[1]
                from_node = self.name

                # Crear mensaje ping con timestamp
                timestamp = time.time()
                ping_msg = Message(
                    proto="control",
                    type="ping",
                    from_node=from_node,
                    to_node=to_node,
                    ttl=1,
                    payload={"timestamp": timestamp}
                )

                # === wait_for_pong aquí ===
                async def wait_for_pong():
                    fut = asyncio.get_event_loop().create_future()

                    async def pong_listener(msg: Message):
                        if msg.mtype == "pong" and msg.from_node == to_node and msg.to_node == from_node:
                            rtt = time.time() - msg.payload["timestamp"]
                            print(f"Ping {from_node} → {to_node}: {rtt:.3f} s")
                            if not fut.done():
                                fut.set_result(True)

                    async with self.nodes[from_node].r.pubsub() as pubsub:
                        await pubsub.subscribe(f"nodo:{from_node}")
                        try:
                            start = time.time()
                            while True:
                                raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                                if raw:
                                    data = raw["data"]
                                    if isinstance(data, str):
                                        msg_obj = Message.from_json(data)
                                    else:
                                        msg_obj = Message.from_json(data.decode() if isinstance(data, bytes) else str(data))
                                    await pong_listener(msg_obj)
                                if time.time() - start > 2:
                                    if not fut.done():
                                        print(f"Ping {from_node} → {to_node}: TIMEOUT")
                                        fut.set_result(False)
                                    break
                                await asyncio.sleep(0.05)
                        except Exception as e:
                            print(f"Error esperando pong: {e}")
                    await fut

                # Enviar ping y esperar pong
                await self.nodes[from_node].send_message(ping_msg)
                await wait_for_pong()


            else:
                print("Comando desconocido. Usa: send, mode, ping, exit")

# ========== MÉTODOS DE CONFIGURACIÓN ==========    
    def load_topology_config(self, filename):
        """
        Cargar topología desde archivo JSON
        Formato esperado: {"type":"topo", "config": {"A": ["B", "C"], ...}}
        """
        try:
            import json
            import os
            
            if not os.path.exists(filename):
                print(f"[{self.name}]   Archivo de topología no encontrado: {filename}")
                return False
                
            with open(filename, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            # Validar formato
            if data.get("type") != "topo":
                print(f"[{self.name}]  Formato incorrecto en {filename}: type debe ser 'topo'")
                return False
                
            if "config" not in data:
                print(f"[{self.name}]  Falta sección 'config' en {filename}")
                return False
                
            topo_config = data["config"]
            
            # Verificar que mi nodo está en la configuración
            if self.name not in topo_config:
                print(f"[{self.name}]  Mi nodo '{self.name}' no está en la topología")
                return False
                
            # Obtener mis vecinos de la configuración
            my_neighbors = topo_config[self.name]
            print(f"[{self.name}]  Topología cargada: mis vecinos son {my_neighbors}")
            
            # Actualizar lista de vecinos (nombres como strings)
            self.neighbors = my_neighbors.copy()
            
            # Guardar información de topología completa (solo para referencia)
            self.topology_config = topo_config
            self.configured_neighbors = my_neighbors
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"[{self.name}]  Error JSON en {filename}: {e}")
            return False
        except Exception as e:
            print(f"[{self.name}]  Error cargando topología: {e}")
            return False

    def load_names_config(self, filename):
        """
        Cargar mapeo de nombres desde archivo JSON
        Formato esperado: {"type":"names", "config": {"A":"foo@bar.com", ...}}
        """
        try:
            import json
            import os
            
            if not os.path.exists(filename):
                print(f"[{self.name}]   Archivo de nombres no encontrado: {filename}")
                return False
                
            with open(filename, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            # Validar formato
            if data.get("type") != "names":
                print(f"[{self.name}]  Formato incorrecto en {filename}: type debe ser 'names'")
                return False
                
            if "config" not in data:
                print(f"[{self.name}]  Falta sección 'config' en {filename}")
                return False
                
            names_config = data["config"]
            
            # Verificar que mi nodo está en la configuración
            if self.name not in names_config:
                print(f"[{self.name}]  Mi nodo '{self.name}' no está en el mapeo de nombres")
                return False
                
            # Obtener mi ID/dirección
            my_address = names_config[self.name]
            print(f"[{self.name}] 🏷️  Mi dirección: {my_address}")
            
            # Guardar mapeo de nombres
            self.names_config = names_config
            self.my_address = my_address
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"[{self.name}]  Error JSON en {filename}: {e}")
            return False
        except Exception as e:
            print(f"[{self.name}]  Error cargando nombres: {e}")
            return False

    async def configure_from_files(self, topo_file=None, names_file=None):
        """
        Configurar nodo usando archivos de configuración (versión async)
        
        Args:
            topo_file (str): Ruta al archivo de topología (ej: "topo-test.txt")
            names_file (str): Ruta al archivo de nombres (ej: "names-test.txt")
        """
        print(f"[{self.name}]  Configurando nodo desde archivos...")
        
        success = True
        
        # Cargar topología si se proporciona
        if topo_file:
            if self.load_topology_config(topo_file):
                print(f"[{self.name}]  Topología cargada correctamente")
                # Actualizar neighbor_costs para LSR
                if self.mode == "lsr":
                    self.neighbor_costs.clear()
                    for neighbor in self.neighbors:
                        self.neighbor_costs[neighbor] = 1  # coste por defecto
            else:
                print(f"[{self.name}]  Error cargando topología")
                success = False
        
        # Cargar nombres si se proporciona  
        if names_file:
            if self.load_names_config(names_file):
                print(f"[{self.name}]  Nombres cargados correctamente")
            else:
                print(f"[{self.name}]  Error cargando nombres")
                success = False
                
        return success

    def get_neighbor_address(self, neighbor_name):
        """
        Obtener la dirección de un vecino usando el mapeo de nombres
        
        Args:
            neighbor_name (str): Nombre del vecino (ej: "B")
            
        Returns:
            str: Dirección del vecino (ej: "nodeB@test.com") o None si no existe
        """
        if not hasattr(self, 'names_config'):
            print(f"[{self.name}]   No hay configuración de nombres cargada")
            return None
            
        return self.names_config.get(neighbor_name)

    def is_configured_neighbor(self, neighbor_name):
        """
        Verificar si un nodo es vecino según la configuración
        
        Args:
            neighbor_name (str): Nombre del nodo a verificar
            
        Returns:
            bool: True si es vecino configurado, False en caso contrario
        """
        if not hasattr(self, 'configured_neighbors'):
            return False
            
        return neighbor_name in self.configured_neighbors

    def print_configuration_status(self):
        """Mostrar estado actual de la configuración"""
        print(f"\n[{self.name}] 📊 ESTADO DE CONFIGURACIÓN:")
        print(f"  └─ Nombre: {self.name}")
        
        if hasattr(self, 'my_address'):
            print(f"  └─ Mi dirección: {self.my_address}")
        else:
            print(f"  └─ Mi dirección: No configurada")
            
        if hasattr(self, 'configured_neighbors'):
            print(f"  └─ Vecinos configurados: {self.configured_neighbors}")
        else:
            print(f"  └─ Vecinos configurados: No cargados")
            
        if hasattr(self, 'neighbors') and self.neighbors:
            print(f"  └─ Vecinos actuales: {self.neighbors}")
        else:
            print(f"  └─ Vecinos actuales: Ninguno")
            
        print(f"  └─ Modo actual: {self.mode}")
        print()
        
    async def periodic_lsp_updates(self, interval: int = 20):
        """Envia LSPs periódicamente cada `interval` segundos"""
        if self.mode != "lsr":
            return
        while True:
            await asyncio.sleep(interval)
            await self.create_and_flood_lsp()

    

# ========== CLI PARA LANZAR UN NODO EN SU PROPIO PROCESO ==========
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python node_redis.py <NAME> [vecino:coste ...]")
        sys.exit(1)

    name = sys.argv[1]
    raw_neighbors = sys.argv[2:]

    # Parseo de vecinos y costos
    neighbors = {}
    for entry in raw_neighbors:
        if ":" in entry:
            neigh, cost = entry.split(":")
            neighbors[neigh] = int(cost)
        else:
            neighbors[entry] = 1  # costo por defecto

    # Crear nodo (modo LSR por defecto)
    node = Node(name, neighbors, mode="lsr")
    node.neighbor_costs = neighbors  # asignar costos directamente

    print(f"[{name}] Iniciando nodo con Redis Async...")
    print(f"[{name}] Vecinos configurados: {neighbors}")
    print(f"[{name}] Modo: {node.mode}")

    async def main():
        try:
            await asyncio.gather(
                node.start(),
                node.initialize_lsr_and_flood(),
                node.periodic_lsp_updates(20),  
                node.console_input()
            )
        except KeyboardInterrupt:
            print(f"\n[{name}] Terminando...")

    asyncio.run(main())
