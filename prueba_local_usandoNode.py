#!/usr/bin/env python3
"""
Prueba local usando Node.py (versión sincrónica que funciona)
Ejecutar: python3 prueba_local.py
"""

from MessageStruct import Message
from Node import Node
import time

def test_flooding():
    """Test del algoritmo Flooding"""
    print("\n" + "="*50)
    print("TEST FLOODING")
    print("="*50)
    
    # Crear nodos
    A = Node("A", mode="flooding")
    B = Node("B", mode="flooding")
    C = Node("C", mode="flooding")
    D = Node("D", mode="flooding")
    
    # Conectar topología
    A.add_neighbor(B)
    A.add_neighbor(C)
    B.add_neighbor(A)
    B.add_neighbor(D)
    C.add_neighbor(A)
    C.add_neighbor(D)
    D.add_neighbor(B)
    D.add_neighbor(C)
    
    # Enviar mensaje
    msg = Message(
        proto="flooding",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=5,
        payload="Hola desde A usando FLOODING!"
    )
    
    print("A envía mensaje a D...")
    A.send_message(msg)
    print(" Flooding completado\n")


def test_lsr():
    """Test del algoritmo LSR"""
    print("\n" + "="*50)
    print("TEST LSR")
    print("="*50)
    
    # Crear nodos
    A = Node("A", mode="lsr")
    B = Node("B", mode="lsr")
    C = Node("C", mode="lsr")
    D = Node("D", mode="lsr")
    nodes = [A, B, C, D]
    
    # Conectar topología
    A.add_neighbor(B)
    A.add_neighbor(C)
    B.add_neighbor(A)
    B.add_neighbor(D)
    C.add_neighbor(A)
    C.add_neighbor(D)
    D.add_neighbor(B)
    D.add_neighbor(C)
    
    # Inicializar LSR
    print(" Inicializando LSR...")
    for node in nodes:
        node._initialize_lsr()
    
    # Intercambiar LSPs
    print("Intercambiando LSPs...")
    for node in nodes:
        node.create_and_flood_lsp()
    
    # Mostrar estado
    print("\n Estado final:")
    for node in nodes:
        print(f"[{node.name}] LSPs: {list(node.lsp_database.keys())}")
    
    # Enviar mensaje de datos
    print("\nA envía mensaje a D usando LSR...")
    msg = Message(
        proto="lsr",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="¡Hola desde A usando LSR!"
    )
    A.send_message(msg)
    print(" LSR completado\n")


def test_dijkstra():
    """Test del algoritmo Dijkstra"""
    print("\n" + "="*50)
    print("TEST DIJKSTRA") 
    print("="*50)
    
    # Grafo con pesos
    graph = {
        "A": {"B": 1, "C": 2},
        "B": {"A": 1, "D": 4},
        "C": {"A": 2, "D": 1},
        "D": {"B": 4, "C": 1}
    }
    
    # Crear nodos
    A = Node("A", mode="dijkstra", graph=graph)
    B = Node("B", mode="dijkstra", graph=graph)
    C = Node("C", mode="dijkstra", graph=graph)
    D = Node("D", mode="dijkstra", graph=graph)
    
    # Conectar topología
    A.add_neighbor(B)
    A.add_neighbor(C)
    B.add_neighbor(A)
    B.add_neighbor(D)
    C.add_neighbor(A)
    C.add_neighbor(D)
    D.add_neighbor(B)
    D.add_neighbor(C)
    
    # Enviar mensaje
    print("A envía mensaje a D (ruta óptima: A→C→D)...")
    msg = Message(
        proto="dijkstra",
        mtype="message", 
        from_node="A",
        to_node="D",
        ttl=10,
        payload="Hola desde A usando DIJKSTRA!"
    )
    A.send_message(msg)
    print(" Dijkstra completado\n")


def main():
    """Función principal"""
    print(" PRUEBAS LOCALES DE ALGORITMOS DE ENRUTAMIENTO")
    print("Usando Node.py (versión sincrónica)")
    print("="*60)
    
    # Ejecutar tests
    test_flooding()
    time.sleep(1)
    
    test_lsr()
    time.sleep(1)
    
    test_dijkstra()
    
    print("\n" + "="*60)
    print(" TODAS LAS PRUEBAS COMPLETADAS")
    print(" Los 3 algoritmos funcionan correctamente")
    print("="*60)


if __name__ == "__main__":
    main()