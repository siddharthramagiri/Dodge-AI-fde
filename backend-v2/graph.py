from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from db import get_connection


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _clean_pk(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _node_id(node_type: str, pk: str) -> str:
    return f"{node_type}:{pk}"


def _add_node(graph: nx.Graph, node_type: str, pk: Optional[str], metadata: Dict[str, Any]) -> Optional[str]:
    if not pk:
        return None
    nid = _node_id(node_type, pk)
    if not graph.has_node(nid):
        graph.add_node(nid, id=nid, type=node_type, metadata=metadata)
    else:
        graph.nodes[nid]["metadata"].update(metadata)
    return nid


def _add_edge(graph: nx.Graph, src_id: Optional[str], dst_id: Optional[str], relation: str) -> None:
    if not src_id or not dst_id or src_id == dst_id:
        return
    graph.add_edge(src_id, dst_id, relation=relation)


def _fetch_rows(conn, sql: str) -> List[Tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def _build_graph() -> nx.Graph:
    g = nx.Graph()
    conn = get_connection()
    try:
        # Build one lookup map for accountingDocument -> billingDocument(s).
        accounting_to_billing: Dict[str, List[str]] = {}
        for billing_document, accounting_document in _fetch_rows(
            conn,
            'SELECT "billingDocument", "accountingDocument" FROM "billing_document_headers"',
        ):
            ad = _clean_pk(accounting_document)
            bd = _clean_pk(billing_document)
            if ad and bd:
                accounting_to_billing.setdefault(ad, []).append(bd)

        for sales_order, sold_to_party, creation_date, total_net_amount in _fetch_rows(
            conn,
            'SELECT "salesOrder", "soldToParty", "creationDate", "totalNetAmount" FROM "sales_order_headers"',
        ):
            so_id = _add_node(
                g,
                "sales_order",
                _clean_pk(sales_order),
                {
                    "salesOrder": _json_safe(sales_order),
                    "soldToParty": _json_safe(sold_to_party),
                    "creationDate": _json_safe(creation_date),
                    "totalNetAmount": _json_safe(total_net_amount),
                },
            )
            bp_id = _add_node(g, "business_partner", _clean_pk(sold_to_party), {"businessPartner": _json_safe(sold_to_party)})
            _add_edge(g, so_id, bp_id, "sales_order_to_business_partner")

        for sales_order, sales_order_item, material, net_amount, requested_qty in _fetch_rows(
            conn,
            'SELECT "salesOrder", "salesOrderItem", "material", "netAmount", "requestedQuantity" FROM "sales_order_items"',
        ):
            soi_id = _add_node(
                g,
                "sales_order_item",
                _clean_pk(f"{sales_order}-{sales_order_item}"),
                {
                    "salesOrder": _json_safe(sales_order),
                    "salesOrderItem": _json_safe(sales_order_item),
                    "material": _json_safe(material),
                    "netAmount": _json_safe(net_amount),
                    "requestedQuantity": _json_safe(requested_qty),
                },
            )
            so_id = _add_node(g, "sales_order", _clean_pk(sales_order), {"salesOrder": _json_safe(sales_order)})
            _add_edge(g, so_id, soi_id, "sales_order_to_items")
            prod_id = _add_node(g, "product", _clean_pk(material), {"material": _json_safe(material)})
            _add_edge(g, soi_id, prod_id, "sales_order_item_to_product")

        for billing_document, sold_to_party, accounting_document, creation_date in _fetch_rows(
            conn,
            'SELECT "billingDocument", "soldToParty", "accountingDocument", "creationDate" FROM "billing_document_headers"',
        ):
            bd_id = _add_node(
                g,
                "billing_document",
                _clean_pk(billing_document),
                {
                    "billingDocument": _json_safe(billing_document),
                    "soldToParty": _json_safe(sold_to_party),
                    "accountingDocument": _json_safe(accounting_document),
                    "creationDate": _json_safe(creation_date),
                },
            )
            bp_id = _add_node(g, "business_partner", _clean_pk(sold_to_party), {"businessPartner": _json_safe(sold_to_party)})
            _add_edge(g, bd_id, bp_id, "billing_document_to_business_partner")

        for billing_document, billing_document_item, sales_order, sales_order_item, material in _fetch_rows(
            conn,
            'SELECT "billingDocument", "billingDocumentItem", "salesOrder", "salesOrderItem", "material" FROM "billing_document_items"',
        ):
            bdi_id = _add_node(
                g,
                "billing_document_item",
                _clean_pk(f"{billing_document}-{billing_document_item}"),
                {
                    "billingDocument": _json_safe(billing_document),
                    "billingDocumentItem": _json_safe(billing_document_item),
                    "salesOrder": _json_safe(sales_order),
                    "salesOrderItem": _json_safe(sales_order_item),
                    "material": _json_safe(material),
                },
            )
            bd_id = _add_node(g, "billing_document", _clean_pk(billing_document), {"billingDocument": _json_safe(billing_document)})
            _add_edge(g, bd_id, bdi_id, "billing_document_to_items")

            soi_id = _add_node(
                g,
                "sales_order_item",
                _clean_pk(f"{sales_order}-{sales_order_item}"),
                {"salesOrder": _json_safe(sales_order), "salesOrderItem": _json_safe(sales_order_item)},
            )
            _add_edge(g, bdi_id, soi_id, "billing_item_to_sales_order_item")

        for delivery_document, creation_date, shipping_point in _fetch_rows(
            conn,
            'SELECT "deliveryDocument", "creationDate", "shippingPoint" FROM "outbound_delivery_headers"',
        ):
            _add_node(
                g,
                "delivery_document",
                _clean_pk(delivery_document),
                {
                    "deliveryDocument": _json_safe(delivery_document),
                    "creationDate": _json_safe(creation_date),
                    "shippingPoint": _json_safe(shipping_point),
                },
            )

        for delivery_document, delivery_document_item, sales_order, sales_order_item, material in _fetch_rows(
            conn,
            'SELECT "deliveryDocument", "deliveryDocumentItem", "salesOrder", "salesOrderItem", "material" FROM "outbound_delivery_items"',
        ):
            odi_id = _add_node(
                g,
                "delivery_document_item",
                _clean_pk(f"{delivery_document}-{delivery_document_item}"),
                {
                    "deliveryDocument": _json_safe(delivery_document),
                    "deliveryDocumentItem": _json_safe(delivery_document_item),
                    "salesOrder": _json_safe(sales_order),
                    "salesOrderItem": _json_safe(sales_order_item),
                    "material": _json_safe(material),
                },
            )
            odh_id = _add_node(g, "delivery_document", _clean_pk(delivery_document), {"deliveryDocument": _json_safe(delivery_document)})
            _add_edge(g, odh_id, odi_id, "delivery_document_to_items")

            soi_id = _add_node(
                g,
                "sales_order_item",
                _clean_pk(f"{sales_order}-{sales_order_item}"),
                {"salesOrder": _json_safe(sales_order), "salesOrderItem": _json_safe(sales_order_item)},
            )
            _add_edge(g, odi_id, soi_id, "delivery_item_to_sales_order_item")

        for accounting_document, accounting_item, customer in _fetch_rows(
            conn,
            'SELECT "accountingDocument", "accountingDocumentItem", "customer" FROM "payments_accounts_receivable"',
        ):
            par_id = _add_node(
                g,
                "payment_ar_item",
                _clean_pk(f"{accounting_document}-{accounting_item}"),
                {
                    "accountingDocument": _json_safe(accounting_document),
                    "accountingDocumentItem": _json_safe(accounting_item),
                    "customer": _json_safe(customer),
                },
            )
            bp_id = _add_node(g, "business_partner", _clean_pk(customer), {"businessPartner": _json_safe(customer)})
            _add_edge(g, par_id, bp_id, "payment_item_to_business_partner")

            ad = _clean_pk(accounting_document)
            for bd in accounting_to_billing.get(ad or "", []):
                bd_id = _add_node(g, "billing_document", _clean_pk(bd), {"billingDocument": _json_safe(bd)})
                _add_edge(g, bd_id, par_id, "billing_document_to_payment_item")

        for accounting_document, accounting_item, customer, gl_account in _fetch_rows(
            conn,
            'SELECT "accountingDocument", "accountingDocumentItem", "customer", "glAccount" FROM "journal_entry_items_accounts_receivable"',
        ):
            jei_id = _add_node(
                g,
                "journal_entry_item",
                _clean_pk(f"{accounting_document}-{accounting_item}"),
                {
                    "accountingDocument": _json_safe(accounting_document),
                    "accountingDocumentItem": _json_safe(accounting_item),
                    "customer": _json_safe(customer),
                    "glAccount": _json_safe(gl_account),
                },
            )
            bp_id = _add_node(g, "business_partner", _clean_pk(customer), {"businessPartner": _json_safe(customer)})
            _add_edge(g, jei_id, bp_id, "journal_entry_item_to_business_partner")

            ad = _clean_pk(accounting_document)
            for bd in accounting_to_billing.get(ad or "", []):
                bd_id = _add_node(g, "billing_document", _clean_pk(bd), {"billingDocument": _json_safe(bd)})
                _add_edge(g, bd_id, jei_id, "billing_document_to_journal_entry_item")

        for bp, full_name, bp_type in _fetch_rows(
            conn,
            'SELECT "businessPartner", "businessPartnerFullName", "businessPartnerType" FROM "business_partners"',
        ):
            _add_node(
                g,
                "business_partner",
                _clean_pk(bp),
                {
                    "businessPartner": _json_safe(bp),
                    "businessPartnerFullName": _json_safe(full_name),
                    "businessPartnerType": _json_safe(bp_type),
                },
            )

        for material, base_unit, material_type, material_group in _fetch_rows(
            conn,
            'SELECT "material", "baseUnit", "materialType", "materialGroup" FROM "products"',
        ):
            _add_node(
                g,
                "product",
                _clean_pk(material),
                {
                    "material": _json_safe(material),
                    "baseUnit": _json_safe(base_unit),
                    "materialType": _json_safe(material_type),
                    "materialGroup": _json_safe(material_group),
                },
            )
    finally:
        conn.close()
    return g


def get_graph() -> Dict[str, List[Dict[str, Any]]]:
    graph = _build_graph()
    nodes = [graph.nodes[n] for n in graph.nodes]
    edges = [
        {"source": u, "target": v, "relation": data.get("relation", "related")}
        for u, v, data in graph.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}


def get_neighbors(node_id: str) -> Dict[str, Any]:
    graph = _build_graph()
    if not graph.has_node(node_id):
        return {"node": None, "neighbors": [], "edges": []}

    neighbors = list(graph.neighbors(node_id))
    neighbor_nodes = [graph.nodes[n] for n in neighbors]
    edges = []
    for n in neighbors:
        edge_data = graph.get_edge_data(node_id, n) or {}
        edges.append(
            {
                "source": node_id,
                "target": n,
                "relation": edge_data.get("relation", "related"),
            }
        )

    return {
        "node": graph.nodes[node_id],
        "neighbors": neighbor_nodes,
        "edges": edges,
    }

