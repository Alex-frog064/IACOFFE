"""Logging centralizado para auditoría y demostración."""

import logging
import sys

LOG_FORMAT = "[%(levelname)s] %(name)s | %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)

audit_logger = logging.getLogger("cafeteria.audit")
state_logger = logging.getLogger("cafeteria.state")
order_logger = logging.getLogger("cafeteria.orders")
sales_logger = logging.getLogger("cafeteria.sales")
tools_logger = logging.getLogger("cafeteria.tools")
