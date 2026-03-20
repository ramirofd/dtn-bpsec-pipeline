from __future__ import annotations

from .models import Contact, Route


def plot_routes(name: str, contact_plan: list[Contact], routes: list[Route], source: int, destination: int) -> None:
    with open(name + "-route-graph.gdf", "w", encoding="utf-8") as f:
        # reset contacts (we use predecessor to store highest depth in path)
        for contact in contact_plan:
            contact.clear_working_area()

        # estimate max_depth and max_arrival_time of each contact
        max_depth = 0
        max_arrival_time = 0
        for route in routes:
            if route.best_delivery_time > max_arrival_time:
                max_arrival_time = route.best_delivery_time
            if len(route.get_hops()) > max_depth:
                max_depth = len(route.get_hops())
            for i, contact in enumerate(route.get_hops()):
                previous_depth = contact.predecessor if isinstance(contact.predecessor, int) else 0
                if previous_depth < (i + 1):
                    contact.predecessor = i + 1

        # write nodes
        height = [0] * (max_depth + 1)
        f.write("nodedef>name VARCHAR,label VARCHAR,x DOUBLE,y DOUBLE,labelvisible BOOLEAN, color VARCHAR\n")
        # root node
        f.write("{},{},{},{},true,green\n".format("root", source, 0, 0))
        for contact in contact_plan:
            depth = contact.predecessor if isinstance(contact.predecessor, int) else 0
            if depth > 0:
                f.write(
                    "{},{},{},{},true,blue\n".format(
                        contact_plan.index(contact),
                        contact,
                        depth * 400,
                        height[depth] * 100,
                    )
                )
                if height[depth] > 0:
                    height[depth] = -height[depth]
                else:
                    height[depth] = -(height[depth] - 1)
        # dst node
        f.write("{},{},{},{},true,green\n".format("dst", destination, (max_depth + 1) * 400, 0))

        f.write("edgedef>node1 VARCHAR,node2 VARCHAR,directed BOOLEAN,weight DOUBLE,color VARCHAR,arr_time DOUBLE\n")
        for route in routes:
            weight = 1
            for i, contact in enumerate(route.get_hops()):
                if i == 0:
                    f.write(
                        "{},{},true,{},'{},{},{}',{}\n".format(
                            "root",
                            contact_plan.index(contact),
                            weight,
                            0,
                            0,
                            0,
                            route.best_delivery_time,
                        )
                    )
                if i > 0:
                    f.write(
                        "{},{},true,{},'{},{},{}',{}\n".format(
                            contact_plan.index(route.get_hops()[i - 1]),
                            contact_plan.index(contact),
                            weight,
                            0,
                            0,
                            0,
                            route.best_delivery_time,
                        )
                    )
                if i == (len(route.get_hops()) - 1):
                    f.write(
                        "{},{},true,{},'{},{},{}',{}\n".format(
                            contact_plan.index(contact),
                            "dst",
                            weight,
                            0,
                            0,
                            0,
                            route.best_delivery_time,
                        )
                    )


def plot_contact_graph(
    name: str,
    contact_plan: list[Contact],
    source: int | None = None,
    destination: int | None = None,
) -> None:
    # determine maximum storage episode
    max_storage_time = 0
    for contact1 in contact_plan:
        for contact2 in contact_plan:
            tx_time = contact1.start
            rx_time = max(contact1.start, contact2.start)
            storage_time = rx_time - tx_time
            if storage_time > max_storage_time:
                max_storage_time = storage_time

    with open(name + "-contact-graph.gdf", "w", encoding="utf-8") as f:
        # write nodes
        f.write("nodedef>name VARCHAR,label VARCHAR,x DOUBLE,y DOUBLE,labelvisible BOOLEAN, color VARCHAR\n")
        for contact in contact_plan:
            f.write("{},{},{},{},true,blue\n".format(contact_plan.index(contact), contact, " ", " "))
        if source is not None:
            f.write("S,{},{},{},true,green\n".format(Contact(source, source, 0, 0, 100, 1.0, 0), " ", " "))
        if destination is not None:
            f.write(
                "D,{},{},{},true,green\n".format(Contact(destination, destination, 0, 0, 100, 1.0, 0), " ", " ")
            )

        # write edges
        f.write("edgedef>node1 VARCHAR,node2 VARCHAR,directed BOOLEAN,color VARCHAR,weight DOUBLE\n")
        for contact1 in contact_plan:
            for contact2 in contact_plan:
                if contact1.to == contact2.frm and contact1.start < contact2.end:
                    index1 = contact_plan.index(contact1)
                    index2 = contact_plan.index(contact2)
                    tx_time = contact1.start
                    rx_time = max(contact1.start, contact2.start)
                    storage_time = rx_time - tx_time
                    f.write("{},{},true,blue,{}\n".format(index1, index2, 1.1 - storage_time / max_storage_time))
            if contact1.frm == source:
                storage_time = contact1.start
                f.write("{},{},true,green,{}\n".format("S", contact_plan.index(contact1), 1.1 - storage_time / max_storage_time))
            if contact1.to == destination:
                storage_time = contact1.start
                f.write("{},{},true,green,{}\n".format(contact_plan.index(contact1), "D", 1.1 - storage_time / max_storage_time))
