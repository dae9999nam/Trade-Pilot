from app.broker.base import Broker
from app.broker.creon import CreonBroker
from app.broker.creon_gateway import CreonGatewayBroker
from app.broker.paper import PaperBroker
from app.core.config import settings


def get_broker() -> Broker:
    if settings.broker_mode == "creon":
        return CreonBroker(settings)
    if settings.broker_mode == "creon_gateway":
        return CreonGatewayBroker(settings)
    return PaperBroker()
