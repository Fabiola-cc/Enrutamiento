#!/usr/bin/env python3
"""
Simulador de Red - VERSIÓN CORREGIDA con timing apropiado
Arregla el problema de race condition en Redis pub/sub
"""

import asyncio
import json
import time
from typing import Dict, List
from node_redis import Node
from MessageStruct import Message

class NetworkSimulator:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.topology = {}
        self.names = {}
        self.running = False
        
    def load_configuration(self, topo_file="topo-test.txt", names_file="names-test.txt"):
        """Cargar configuración completa de la red"""
        print("🔧 Cargando configuración de la red...")
        
        # Cargar topología
        try:
            with open(topo_file, 'r') as f:
                topo_data = json.load(f)
                self.topology = topo_data["config"]
                print(f" Topología cargada: {list(self.topology.keys())}")
        except Exception as e:
            print(f" Error cargando topología: {e}")
            return False
            
        # Cargar nombres
        try:
            with open(names_file, 'r') as f:
                names_data = json.load(f)
                self.names = names_data["config"]
                print(f" Nombres cargados: {len(self.names)} nodos")
        except Exception as e:
            print(f" Error cargando nombres: {e}")
            return False
            
        return True
    
    async def create_all_nodes(self, mode="lsr"):
        """Crear todos los nodos automáticamente"""
        print(f"\n🚀 Creando nodos en modo '{mode}'...")
        
        for node_name in self.topology.keys():
            # Crear nodo
            node = Node(node_name, mode=mode)
            
            # Configurar desde archivos
            success = await node.configure_from_files("topo-test.txt", "names-test.txt")
            if success:
                self.nodes[node_name] = node
                print(f" Nodo {node_name} creado y configurado")
            else:
                print(f" Error configurando nodo {node_name}")
                return False
                
        print(f" {len(self.nodes)} nodos creados exitosamente")
        return True
    
    async def start_network_listeners(self):
        """Iniciar listeners de Redis en todos los nodos"""
        print("\n Iniciando listeners de la red...")
        
        # Crear tareas para escuchar en cada nodo
        tasks = []
        for node_name, node in self.nodes.items():
            task = asyncio.create_task(node.start())
            tasks.append(task)
            print(f" Listener iniciado para nodo {node_name}")
        
        # CRÍTICO: Esperar a que todos los listeners estén listos
        print("Esperando a que los listeners estén completamente listos...")
        await asyncio.sleep(3)  # Dar tiempo para que se establezcan las suscripciones
        
        self.running = True
        return tasks
    
    async def initialize_network(self):
        """Inicializar algoritmos de enrutamiento en todos los nodos"""
        print("\nInicializando algoritmos de enrutamiento...")
        
        # PASO 1: Solo inicializar LSR local (sin flooding aún)
        for node_name, node in self.nodes.items():
            if node.mode == "lsr":
                node._initialize_lsr()  # Solo configuración local
                print(f" LSR configurado localmente en nodo {node_name}")
        
        # PASO 2: Ahora sí hacer el flooding (después de que listeners estén listos)
        print(" Iniciando flooding de LSPs...")
        for node_name, node in self.nodes.items():
            if node.mode == "lsr":
                await node.create_and_flood_lsp()
                print(f" LSPs enviados desde nodo {node_name}")
                await asyncio.sleep(0.5)  # Pequeña pausa entre envíos
        
        # PASO 3: Esperar propagación completa
        print("Esperando propagación completa de LSPs...")
        await asyncio.sleep(3)
        
        # PASO 4: Verificar que todos tengan la topología completa
        print(" Verificando estado de topologías:")
        for node_name, node in self.nodes.items():
            if node.mode == "lsr":
                topo_size = len(node.topology_graph)
                expected_size = len(self.topology)
                status = "" if topo_size == expected_size else ""
                print(f"   {status} {node_name}: {topo_size}/{expected_size} nodos conocidos")
                if hasattr(node, 'prev') and node.prev:
                    routes = [k for k, v in node.prev.items() if v is not None or k == node_name]
                    print(f"        Rutas disponibles a: {routes}")
            
        print("Red inicializada y estabilizada")
    
    async def send_message(self, from_node, to_node, message):
        """Enviar mensaje desde un nodo a otro"""
        if from_node not in self.nodes:
            print(f" Nodo origen '{from_node}' no existe")
            return False
            
        if to_node not in self.nodes:
            print(f" Nodo destino '{to_node}' no existe")
            return False
        
        # Crear mensaje

        
        msg = Message(
            proto=self.nodes[from_node].mode,
            mtype="message",
            from_node=from_node,
            to_node=to_node,
            ttl=10,
            payload=message
        )
        
        print(f"\n Enviando mensaje: {from_node} → {to_node}")
        print(f"   Contenido: {message}")
        print(f"   Algoritmo: {self.nodes[from_node].mode}")
        
        # Verificar que el nodo origen tiene rutas
        sender_node = self.nodes[from_node]
        if sender_node.mode == "lsr":
            if not hasattr(sender_node, 'prev') or not sender_node.prev:
                print(" El nodo origen no tiene tabla de rutas. Reintentando inicialización...")
                await sender_node.initialize_lsr_and_flood()
                await asyncio.sleep(2)
        
        # Enviar mensaje
        await self.nodes[from_node].send_message(msg)
        return True
    
    def print_network_status(self):
        """Mostrar estado actual de la red"""
        print("\n" + "="*60)
        print(" ESTADO DE LA RED")
        print("="*60)
        
        print(f"Nodos activos: {len(self.nodes)}")
        print(f"🔗 Topología:")
        for node_name, neighbors in self.topology.items():
            status = "🟢" if node_name in self.nodes else "🔴"
            print(f"   {status} {node_name}: {neighbors}")
            
        print(f"\n📍 Direcciones:")
        for node_name, address in self.names.items():
            status = "🟢" if node_name in self.nodes else "🔴"
            print(f"   {status} {node_name}: {address}")
            
        print(f"\n  Modos de enrutamiento:")
        for node_name, node in self.nodes.items():
            print(f"   🔧 {node_name}: {node.mode}")
            
        # NUEVO: Mostrar estado de tablas de enrutamiento
        print(f"\n  Estado de tablas de enrutamiento:")
        for node_name, node in self.nodes.items():
            if hasattr(node, 'topology_graph'):
                known_nodes = len(node.topology_graph)
                total_nodes = len(self.topology)
                print(f"    {node_name}: conoce {known_nodes}/{total_nodes} nodos")
                if hasattr(node, 'prev') and node.prev:
                    reachable = [k for k, v in node.prev.items() if v is not None or k == node_name]
                    print(f"      Puede llegar a: {reachable}")
        print()
    
    async def interactive_mode(self):
        """Modo interactivo para enviar mensajes"""
        print("\n" + "="*60)
        print(" MODO INTERACTIVO - ENVÍO DE MENSAJES")
        print("="*60)
        print("Comandos disponibles:")
        print("  send <origen> <destino> <mensaje>  - Enviar mensaje")
        print("  status                             - Ver estado de la red")
        print("  topology                          - Ver topología")
        print("  mode <nodo> <algoritmo>           - Cambiar algoritmo de un nodo")
        print("  refresh                           - Reinicializar LSR")
        print("  exit                              - Salir")
        print()
        
        while self.running:
            try:
                user_input = input("Network > ").strip()
                if not user_input:
                    continue
                    
                parts = user_input.split()
                cmd = parts[0].lower()
                
                if cmd == "exit":
                    print("👋 Cerrando simulador...")
                    self.running = False
                    break
                    
                elif cmd == "send":
                    if len(parts) < 4:
                        print(" Uso: send <origen> <destino> <mensaje>")
                        continue
                    from_node = parts[1]
                    to_node = parts[2] 
                    message = " ".join(parts[3:])
                    await self.send_message(from_node, to_node, message)
                    
                elif cmd == "status":
                    self.print_network_status()
                    
                elif cmd == "topology":
                    print("\n  TOPOLOGÍA VISUAL:")
                    self.print_topology_visual()
                    
                elif cmd == "refresh":
                    print("Reinicializando red...")
                    await self.initialize_network()
                    
                elif cmd == "mode":
                    if len(parts) < 3:
                        print(" Uso: mode <nodo> <flooding|lsr|dijkstra>")
                        continue
                    node_name = parts[1]
                    new_mode = parts[2]
                    if node_name in self.nodes:
                        old_mode = self.nodes[node_name].mode
                        self.nodes[node_name].mode = new_mode
                        print(f" Nodo {node_name}: {old_mode} → {new_mode}")
                        if new_mode == "lsr":
                            await self.nodes[node_name].initialize_lsr_and_flood()
                    else:
                        print(f" Nodo '{node_name}' no existe")
                        
                else:
                    print(" Comando desconocido. Usa: send, status, topology, mode, refresh, exit")
                    
            except KeyboardInterrupt:
                print("\n👋 Cerrando simulador...")
                self.running = False
                break
            except Exception as e:
                print(f" Error: {e}")
    
    def print_topology_visual(self):
        """Imprimir representación visual de la topología"""
        print("\nConexiones:")
        for node, neighbors in self.topology.items():
            print(f"  {node} ←→ {', '.join(neighbors)}")
        print()

async def main():
    """Función principal del simulador"""
    print("SIMULADOR DE RED - ALGORITMOS DE ENRUTAMIENTO (VERSIÓN CORREGIDA)")
    print("="*70)
    
    # Crear simulador
    simulator = NetworkSimulator()
    
    # Cargar configuración
    if not simulator.load_configuration():
        print(" Error en configuración. Saliendo...")
        return
        
    # Crear nodos
    if not await simulator.create_all_nodes(mode="lsr"):  # Cambiar mode aquí
        print(" Error creando nodos. Saliendo...")
        return
        
    # ORDEN CORREGIDO: Primero iniciar listeners, luego algoritmos
    # Iniciar listeners en background
    listener_tasks = await simulator.start_network_listeners()
    
    # Después inicializar red (cuando listeners estén listos)
    await simulator.initialize_network()
    
    # Mostrar estado
    simulator.print_network_status()
    
    # Ejecutar modo interactivo
    try:
        await simulator.interactive_mode()
    finally:
        # Cancelar todas las tareas
        for task in listener_tasks:
            task.cancel()
        print(" Simulador cerrado correctamente")

if __name__ == "__main__":
    asyncio.run(main())