import re

from models.conversation_state import OrderStatus
from services.activity_service import log_activity
from services.conversation_state_service import get_conversation_state, save_conversation_state
from services.ollama_service import OllamaService
from tools.order_tools import cancel_order, get_active_order, get_user_orders

CANCEL_INTENT = re.compile(
    r"\b(cancelar\s+(mi\s+)?pedido|anular\s+(mi\s+)?pedido|ya\s+no\s+lo\s+quiero|"
    r"no\s+lo\s+quiero|cancelar\s+orden)\b",
    re.IGNORECASE,
)

CONFIRM_YES = re.compile(
    r"^(s[ií]|confirmo|correcto|dale|ok|okay|de\s+acuerdo|claro|afirmativo)\b",
    re.IGNORECASE,
)

CONFIRM_NO = re.compile(
    r"^(no|nop|mejor\s+no|olvidalo|olvídalo)\b",
    re.IGNORECASE,
)

NON_CANCELLABLE = {
    OrderStatus.PREPARING.value,
    OrderStatus.DELIVERING.value,
    OrderStatus.COMPLETED.value,
}

CANCELLABLE = {OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value}


class CancelService:
    def __init__(self, ollama: OllamaService | None = None):
        self.ollama = ollama or OllamaService()

    def is_cancel_intent(self, message: str) -> bool:
        return bool(CANCEL_INTENT.search(message.strip()))

    async def handle(
        self,
        user_id: int,
        conversation_id: str,
        user_message: str,
        history: list[dict],
    ) -> tuple[str, list[str], str] | None:
        state_data = get_conversation_state(conversation_id)
        collected = state_data.get("collected") or {}
        pending_id = collected.get("pending_cancel_order_id")

        if pending_id and (CONFIRM_YES.search(user_message.strip()) or CONFIRM_NO.search(user_message.strip())):
            return await self._handle_confirmation(
                user_id, conversation_id, user_message, history, int(pending_id), state_data
            )

        if not self.is_cancel_intent(user_message):
            return None

        order = self._find_cancellable_order(user_id, conversation_id)
        if not order:
            response = await self.ollama.generate_employee_response(
                instruction="Informa amablemente que no encontraste un pedido activo para cancelar.",
                context="Sin pedidos cancelables.",
                history=history,
            )
            return response, [], state_data["state"]

        if order["status"] in NON_CANCELLABLE:
            response = await self.ollama.generate_employee_response(
                instruction=(
                    f"Explica amablemente que el pedido #{order['id']} está en estado {order['status']} "
                    "y ya no puede cancelarse porque está en preparación o entrega."
                ),
                context=f"Pedido #{order['id']} status={order['status']}",
                history=history,
            )
            return response, [], state_data["state"]

        if order["status"] not in CANCELLABLE:
            response = await self.ollama.generate_employee_response(
                instruction=f"Informa que el pedido #{order['id']} no puede cancelarse (estado: {order['status']}).",
                context="",
                history=history,
            )
            return response, [], state_data["state"]

        save_conversation_state(conversation_id, pending_cancel_order_id=order["id"])
        response = await self.ollama.generate_employee_response(
            instruction=f"Pregunta ÚNICAMENTE: ¿Deseas cancelar tu pedido #{order['id']}? Responde sí o no.",
            context=f"Pedido #{order['id']} en estado {order['status']}",
            history=history,
        )
        return response, ["cancel_order"], state_data["state"]

    async def _handle_confirmation(
        self,
        user_id: int,
        conversation_id: str,
        user_message: str,
        history: list[dict],
        order_id: int,
        state_data: dict,
    ) -> tuple[str, list[str], str]:
        save_conversation_state(conversation_id, pending_cancel_order_id=None)

        if CONFIRM_NO.search(user_message.strip()):
            response = await self.ollama.generate_employee_response(
                instruction="Confirma amablemente que el pedido se mantiene activo.",
                context=f"Pedido #{order_id} no cancelado.",
                history=history,
            )
            return response, [], state_data["state"]

        order = _get_order_if_owner(order_id, user_id)
        if not order:
            return "No tienes permiso para cancelar ese pedido.", [], state_data["state"]

        result = cancel_order(order_id, user_id=user_id)
        if not result.get("exito"):
            response = await self.ollama.generate_employee_response(
                instruction=f"Explica el problema: {result.get('mensaje')}",
                context="",
                history=history,
            )
            return response, ["cancel_order"], state_data["state"]

        log_activity(user_id, "CANCEL_ORDER", {"order_id": order_id})
        response = await self.ollama.generate_employee_response(
            instruction=(
                f"Confirma amablemente que el pedido #{order_id} fue cancelado exitosamente. "
                "Ofrece ayuda si desea hacer un nuevo pedido."
            ),
            context=f"Pedido #{order_id} CANCELLED",
            history=history,
        )
        return response, ["cancel_order"], state_data["state"]

    def _find_cancellable_order(self, user_id: int, conversation_id: str) -> dict | None:
        active = get_active_order(conversation_id)
        if active.get("pedido") and active["pedido"].get("user_id") == user_id:
            return active["pedido"]

        orders = get_user_orders(user_id, limit=5)
        for order in orders:
            if order["status"] in CANCELLABLE or order["status"] in NON_CANCELLABLE:
                return order
        return None


def _get_order_if_owner(order_id: int, user_id: int) -> dict | None:
    from database.db import get_db

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?",
            (order_id, user_id),
        ).fetchone()
    return dict(row) if row else None
