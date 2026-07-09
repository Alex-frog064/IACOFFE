OLLAMA_ADMIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_inventario",
            "description": "Consulta el inventario completo de la cafetería: productos, stock, precios y mínimos.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_venta",
            "description": "Registra una venta de un producto y descuenta del inventario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto": {
                        "type": "string",
                        "description": "Nombre del producto vendido (ej: Café molido, Croissant).",
                    },
                    "cantidad": {
                        "type": "number",
                        "description": "Cantidad vendida.",
                    },
                },
                "required": ["producto", "cantidad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_gasto",
            "description": "Registra un gasto operativo de la cafetería (proveedores, servicios, insumos, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "concepto": {
                        "type": "string",
                        "description": "Descripción del gasto.",
                    },
                    "monto": {
                        "type": "number",
                        "description": "Monto del gasto en la moneda local.",
                    },
                },
                "required": ["concepto", "monto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_producto_mas_vendido",
            "description": "Obtiene el producto más vendido históricamente con cantidades e ingresos.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_ganancia_dia",
            "description": "Calcula ingresos, gastos y ganancia neta del día actual.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "productos_bajo_stock",
            "description": "Lista productos cuyo stock está en o por debajo del mínimo configurado.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recomendar_compra",
            "description": "Genera recomendaciones de compra para productos con stock bajo.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

ADMIN_SYSTEM_PROMPT = """Eres Cafetería IA en modo administrador.

Eres un asistente amigable y conversacional. Hablas español de México.
Ayudas con inventario, ventas, gastos, ganancias, pedidos y recomendaciones de compra.

Cuando el usuario pregunte datos del negocio, usa las herramientas disponibles.
Responde de forma clara, breve y natural.
Presenta los datos de forma legible (listas, totales, resúmenes).
Si una operación falla, explica el error al usuario.
No fuerces pedidos; solo menciona pedidos si el usuario lo pide."""
