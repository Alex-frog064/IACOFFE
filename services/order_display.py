"""Helpers de presentación para pedidos (sin lógica de negocio)."""


def estimated_minutes(delivery_type: str | None) -> int:
    dt = (delivery_type or "").lower()
    if "domicilio" in dt or "delivery" in dt:
        return 30
    return 15


def build_order_card(order: dict) -> dict:
    items = order.get("items") or []
    return {
        "order_id": order["id"],
        "customer_name": order.get("customer_name") or "Cliente",
        "items": items,
        "total": float(order.get("total") or 0),
        "status": order.get("status") or "PENDING",
        "delivery_type": order.get("delivery_type"),
        "estimated_minutes": estimated_minutes(order.get("delivery_type")),
        "created_at": order.get("created_at"),
    }
