from abc import ABC, abstractmethod
from typing import Optional, Sequence

from db import DbSession
from event_store.message_store import MessageStore
from event_store.subscription import Subscription


# Класс `Launcher` инкапсулирует связанную бизнес-логику.
class Launcher(ABC):
    message_store: MessageStore
    db_session: Optional[DbSession]
    subscriptions: Sequence[Subscription]

    # Функция `__init__` реализует локальную часть бизнес-логики модуля.
    def __init__(
        self,
        message_store: MessageStore,
        db_session: Optional[DbSession] = None,
    ) -> None:
        self.message_store = message_store
        self.db_session = db_session
        self.init_subscriptions()

    @abstractmethod
    # Функция `init_subscriptions` реализует локальную часть бизнес-логики модуля.
    def init_subscriptions(self) -> None:
        pass  # pragma: no cover

    @abstractmethod
    async def start(self) -> None:
        pass  # pragma: no cover

    @abstractmethod
    # Функция `stop` реализует локальную часть бизнес-логики модуля.
    def stop(self) -> None:
        pass  # pragma: no cover
