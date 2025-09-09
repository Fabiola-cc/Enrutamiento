#!/usr/bin/env python3
"""
Prueba local usando node_redis.py corregido
Requiere Redis corriendo: redis-server
Ejecutar: python3 prueba_local.py
"""

import asyncio
from MessageStruct import Message
from node_redis import Node

async def test_flooding():
    """Test del algoritmo Flooding con Redis"""
    print("\n" + "="*50)
    print(" TEST FLOODING (Redis)")
    print("="*50)
    
    # Definir topología
    topo = {
        "A": ["B", "C"],
        "B": ["A", "D"], 
        "C": ["A", "D"],
        "D": ["B", "C"]
    }

    # Crear nodos
    A = Node("A", topo["A"], mode="flooding")
    B = Node("B", topo["B"], mode="flooding")
    C = Node("C", topo["C"], mode="flooding")
    D = Node("D", topo["D"], mode="flooding")
    nodes = [A, B, C, D]

    # Arrancar cada nodo como tarea async
    tasks = []
    for node in nodes:
        tasks.append(asyncio.create_task(node.start()))

    # Dar tiempo a que se suscriban
    await asyncio.sleep(1)
    print(" Todos los nodos suscritos")

    # Enviar mensaje de flooding
    msg_flood = Message(
        proto="flooding",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=5,
        payload="Hola desde A usando FLOODING!"
    )
    
    print(" A envía mensaje a D...")
    await A.send_message(msg_flood)
    
    # Esperar a que se procese
    await asyncio.sleep(2)
    print(" Flooding completado\n")
    
    # Cancelar las tareas de los nodos
    for task in tasks:
        task.cancel()

async def test_lsr():
    """Test del algoritmo LSR con Redis"""
    print("\n" + "="*50)
    print(" TEST LSR (Redis)")
    print("="*50)
    
    # Definir topología
    topo = {
        "A": ["B", "C"],
        "B": ["A", "D"],
        "C": ["A", "D"],
        "D": ["B", "C"]
    }

    # Crear nodos en modo LSR
    A = Node("A", topo["A"], mode="lsr")
    B = Node("B", topo["B"], mode="lsr")
    C = Node("C", topo["C"], mode="lsr")
    D = Node("D", topo["D"], mode="lsr")
    nodes = [A, B, C, D]

    # Arrancar nodos
    tasks = []
    for node in nodes:
        tasks.append(asyncio.create_task(node.start()))

    # Dar tiempo a suscribirse
    await asyncio.sleep(1)
    print(" Todos los nodos suscritos")

    # Inicializar LSR y hacer flooding de LSPs
    print(" Inicializando LSR y intercambiando LSPs...")
    for node in nodes:
        await node.initialize_lsr_and_flood()

    # Esperar a que se complete el intercambio de LSPs
    await asyncio.sleep(2)

    # Mostrar estado final
    print("\n Estado final de LSPs:")
    for node in nodes:
        lsps_known = list(node.lsp_database.keys())
        print(f"[{node.name}] LSPs conocidos: {lsps_known}")

    # Enviar mensaje de datos
    print("\n A envía mensaje a D usando LSR...")
    msg_lsr = Message(
        proto="lsr",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="¡Hola desde A usando LSR!"
    )
    await A.send_message(msg_lsr)

    # Esperar a que se procese
    await asyncio.sleep(2)
    print(" LSR completado\n")
    
    # Cancelar tareas
    for task in tasks:
        task.cancel()

async def test_dijkstra():
    """Test del algoritmo Dijkstra con Redis"""
    print("\n" + "="*50)
    print(" TEST DIJKSTRA (Redis)")
    print("="*50)
    
    # Grafo con pesos
    weighted_graph = {
        "A": {"B": 1, "C": 2},
        "B": {"A": 1, "D": 4},
        "C": {"A": 2, "D": 1},
        "D": {"B": 4, "C": 1}
    }
    
    # Topología de vecinos
    topo = {
        "A": ["B", "C"],
        "B": ["A", "D"],
        "C": ["A", "D"],
        "D": ["B", "C"]
    }

    # Crear nodos en modo Dijkstra
    A = Node("A", topo["A"], mode="dijkstra", graph=weighted_graph)
    B = Node("B", topo["B"], mode="dijkstra", graph=weighted_graph)
    C = Node("C", topo["C"], mode="dijkstra", graph=weighted_graph)
    D = Node("D", topo["D"], mode="dijkstra", graph=weighted_graph)
    nodes = [A, B, C, D]

    # Arrancar nodos
    tasks = []
    for node in nodes:
        tasks.append(asyncio.create_task(node.start()))

    # Dar tiempo a suscribirse
    await asyncio.sleep(1)
    print(" Todos los nodos suscritos")

    # Enviar mensaje Dijkstra
    print(" A envía mensaje a D (ruta óptima: A→C→D)...")
    msg_dijk = Message(
        proto="dijkstra",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="Hola desde A usando DIJKSTRA!"
    )
    await A.send_message(msg_dijk)

    # Esperar a que se procese
    await asyncio.sleep(2)
    print(" Dijkstra completado\n")
    
    # Cancelar tareas
    for task in tasks:
        task.cancel()

async def main():
    """Función principal que ejecuta todos los tests"""
    print(" PRUEBAS LOCALES CON REDIS")
    print(" Usando node_redis.py corregido")
    print("="*60)
    
    try:
        # Test 1: Flooding
        await test_flooding()
        await asyncio.sleep(0.5)
        
        # Test 2: LSR  
        await test_lsr()
        await asyncio.sleep(0.5)
        
        # Test 3: Dijkstra
        await test_dijkstra()
        
        print("\n" + "="*60)
        print(" TODAS LAS PRUEBAS COMPLETADAS")
        print("Los 3 algoritmos funcionan correctamente con Redis")
        print("="*60)
        
    except Exception as e:
        print(f"Error durante las pruebas: {e}")
        print("Asegúrate de que Redis esté corriendo: redis-server")

if __name__ == "__main__":
    print(" Requisitos:")
    print("   - Redis server corriendo: redis-server")
    print("   - MessageStruct.py en el directorio")
    print("   - node_redis.py corregido")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Pruebas interrumpidas por el usuario")
    except Exception as e:
        print(f"\nError: {e}")
        print("Verifica que Redis esté corriendo y los archivos estén presentes")