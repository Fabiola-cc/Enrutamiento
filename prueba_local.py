import asyncio
from MessageStruct import Message
from node_redis import Node

async def main():
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

    # Arrancar cada nodo como tarea
    for node in nodes:
        asyncio.create_task(node.start())

    await asyncio.sleep(1)  # dar tiempo a que se suscriban

    # ---------------- Ejemplo Flooding ----------------
    print("\n=== TEST FLOODING ===\n")
    msg_flood = Message(
        proto="flooding",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=5,
        payload="Hola desde A usando FLOODING!"
    )
    await A.send_message(msg_flood)

    await asyncio.sleep(3)

    # ---------------- Ejemplo LSR ----------------
    print("\n=== TEST LSR ===\n")
    for n in nodes:
        n.mode = "lsr"
        n._initialize_lsr()

    # Forzar que todos creen y flooden su LSP
    for n in nodes:
        await n.trigger_lsp_update()

    await asyncio.sleep(2)

    msg_lsr = Message(
        proto="lsr",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="¡Hola desde A usando LSR!"
    )
    await A.send_message(msg_lsr)

    await asyncio.sleep(3)

    # ---------------- Ejemplo Dijkstra ----------------
    print("\n=== TEST DIJKSTRA ===\n")
    weighted_graph = {
        "A": {"B": 1, "C": 2},
        "B": {"A": 1, "D": 4},
        "C": {"A": 2, "D": 1},
        "D": {"B": 4, "C": 1}
    }
    for n in nodes:
        n.mode = "dijkstra"
        n.graph = weighted_graph
        n._dijkstra()

    msg_dijk = Message(
        proto="dijkstra",
        mtype="message",
        from_node="A",
        to_node="D",
        ttl=10,
        payload="Hola desde A usando DIJKSTRA!"
    )
    await A.send_message(msg_dijk)

    # Mantener el cluster corriendo un rato
    await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())