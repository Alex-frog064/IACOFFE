from models.user import UserRole
from services.intent_service import (
    get_capabilities_text,
    is_capabilities_question,
    is_farewell,
    is_greeting,
    is_hours_question,
    is_identity_question,
    is_menu_request,
    is_product_inquiry,
    is_stock_inquiry,
)
from services.ollama_service import OllamaService
from tools.cafe_tools import obtener_menu


class GeneralChatService:
    def __init__(self, ollama: OllamaService | None = None):
        self.ollama = ollama or OllamaService()

    def _build_context(self, message: str, role: str) -> str:
        parts: list[str] = []

        if is_menu_request(message):
            menu = obtener_menu().get("productos") or []
            if menu:
                lines = [
                    f"- {p['nombre']}: ${p['precio']:.2f} (stock: {int(p['stock'])})"
                    for p in menu
                ]
                parts.append("Menú activo de la cafetería:\n" + "\n".join(lines))
            else:
                parts.append("No hay productos activos en el menú en este momento.")

        elif is_product_inquiry(message):
            menu = obtener_menu().get("productos") or []
            if menu:
                lines = [
                    f"- {p['nombre']}: ${p['precio']:.2f} (stock: {int(p['stock'])})"
                    for p in menu
                ]
                parts.append("Menú activo de la cafetería:\n" + "\n".join(lines))
            else:
                parts.append("No hay productos activos en el menú en este momento.")

        elif is_stock_inquiry(message):
            menu = obtener_menu().get("productos") or []
            if menu:
                lines = [
                    f"- {p['nombre']}: {int(p['stock'])} unidades disponibles"
                    for p in menu
                ]
                parts.append("Stock disponible de la cafetería:\n" + "\n".join(lines))
            else:
                parts.append("No hay productos activos en el menú en este momento.")

        if is_capabilities_question(message):
            parts.append(get_capabilities_text(role))

        if is_hours_question(message):
            parts.append(
                "Horario de la cafetería: lunes a domingo de 8:00 a 22:00 hrs. "
                "Los pedidos solo se pueden realizar de 19:00 (7 PM) a 22:00 (10 PM)."
            )

        if is_identity_question(message):
            parts.append(
                "Tu nombre es Cafetería IA. Eres el asistente virtual amigable de la cafetería."
            )

        if is_greeting(message):
            parts.append("El usuario te saluda. Responde cálido y pregunta en qué puedes ayudar.")

        if is_farewell(message):
            parts.append("El usuario se despide. Responde breve y amable.")

        if role == UserRole.ADMIN.value:
            parts.append("El usuario autenticado es administrador.")
        else:
            parts.append("El usuario autenticado es cliente.")

        if not parts:
            parts.append(
                "Responde de forma natural al mensaje. No insistas en que haga un pedido "
                "a menos que él lo pida."
            )

        return "\n\n".join(parts)

    async def handle(
        self,
        message: str,
        role: str,
        history: list[dict[str, str]],
    ) -> str:
        if is_menu_request(message):
            return self._render_menu()

        if is_stock_inquiry(message):
            return self._render_stock()

        context = self._build_context(message, role)
        try:
            return await self.ollama.generate_conversational_response(
                message, context, history
            )
        except Exception:
            return self._fallback(message, role)

    def _render_menu(self) -> str:
        menu = obtener_menu().get("productos") or []
        if not menu:
            return "Por ahora no tenemos productos activos en el menú. ¿Te ayudo con algo más?"
        lines = [f"- {p['nombre']}: ${p['precio']:.2f}" for p in menu]
        return "Este es nuestro menú disponible:\n" + "\n".join(lines)

    def _render_stock(self) -> str:
        menu = obtener_menu().get("productos") or []
        if not menu:
            return "Por ahora no tenemos productos activos en el menú. ¿Te ayudo con algo más?"
        lines = [f"- {p['nombre']}: {int(p['stock'])} unidades disponibles (${p['precio']:.2f} c/u)" for p in menu]
        return "📦 Este es el stock disponible de nuestros productos:\n" + "\n".join(lines) + "\n\n¿Te gustaría hacer un pedido?"

    def _fallback(self, message: str, role: str) -> str:
        text = message.strip().lower()

        if is_menu_request(message):
            return self._render_menu()

        if is_greeting(message):
            return "¡Hola! Soy Cafetería IA, el asistente de la cafetería. ¿En qué te puedo ayudar hoy?"

        if is_farewell(message):
            return "¡Hasta pronto! Que tengas un excelente día. ☕"

        if is_identity_question(message):
            return (
                "Soy Cafetería IA, el asistente virtual de la cafetería. "
                "Estoy aquí para platicar contigo, resolver dudas y ayudarte con pedidos cuando lo necesites."
            )

        if is_capabilities_question(message):
            caps = get_capabilities_text(role)
            return f"Claro, te cuento. {caps} ¿Qué te gustaría hacer?"

        if is_hours_question(message):
            return (
                "Abrimos de lunes a domingo, de 8:00 a 22:00 hrs. "
                "Los pedidos solo se pueden realizar de 7:00 PM a 10:00 PM."
            )

        if is_stock_inquiry(message):
            return self._render_stock()

        if is_product_inquiry(message):
            menu = obtener_menu().get("productos") or []
            if not menu:
                return "Por ahora no tenemos productos activos en el menú. ¿Te ayudo con algo más?"
            preview = ", ".join(p["nombre"] for p in menu[:6])
            extra = f" y {len(menu) - 6} más" if len(menu) > 6 else ""
            return (
                f"Tenemos en el menú: {preview}{extra}. "
                f"¿Te gustaría conocer precios o hacer un pedido?"
            )

        if any(term in text for term in [
            "mundial", "programación", "historia", "videojuegos", "deportes", "política", 
            "clima", "noticias", "medicina", "tecnología", "tareas",
        ]):
            return (
                "Soy el asistente virtual de Cafetería IA y únicamente puedo ayudarte con información relacionada con nuestro menú, productos y servicios. "
                "Si gustas, puedo mostrarte nuestras bebidas, alimentos, postres o promociones disponibles."
            )

        if "gracias" in text:
            return "¡De nada! Para lo que necesites."

        return (
            "Entiendo. Si quieres, puedo contarte del menú, horarios o ayudarte con un pedido. "
            "¿Qué te gustaría saber?"
        )
