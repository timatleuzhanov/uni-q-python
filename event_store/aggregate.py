from abc import ABC, abstractmethod

from event_store.message import Message
from event_store.types import JSON


# Класс `Aggregate` инкапсулирует связанную бизнес-логику.
class Aggregate(ABC):
    _position: int = -1
    _global_position: int = -1
    _source_position: int = -1

    @property
    # Функция `position` реализует локальную часть бизнес-логики модуля.
    def position(self) -> int:
        return self._position

    @property
    # Функция `global_position` реализует локальную часть бизнес-логики модуля.
    def global_position(self) -> int:
        return self._global_position

    @property
    # Функция `source_position` реализует локальную часть бизнес-логики модуля.
    def source_position(self) -> int:
        return self._source_position

    @classmethod
    @abstractmethod
    # Функция `create` реализует локальную часть бизнес-логики модуля.
    def create(cls) -> "Aggregate":
        pass  # pragma: no cover

    # Функция `apply` реализует локальную часть бизнес-логики модуля.
    def apply(self, message: Message) -> "Aggregate":
        assert message.position is not None
        assert message.position > self._position
        new_aggregate = self._apply(message=message)
        new_aggregate._position = message.position
        new_aggregate._global_position = message.global_position
        origin_position = message.metadata.get("origin")
        if isinstance(origin_position, int):
            new_aggregate._source_position = origin_position
        return new_aggregate

    @abstractmethod
    # Функция `_apply` реализует локальную часть бизнес-логики модуля.
    def _apply(self, message: Message) -> "Aggregate":
        pass  # pragma: no cover

    @abstractmethod
    # Функция `to_json` реализует локальную часть бизнес-логики модуля.
    def to_json(self) -> JSON:
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    # Функция `from_json` реализует локальную часть бизнес-логики модуля.
    def from_json(cls, data: JSON) -> "Aggregate":
        pass  # pragma: no cover

    @classmethod
    # Функция `get_aggregate_name` получает и возвращает вычисленные/запрошенные данные.
    def get_aggregate_name(cls) -> str:
        """
        This aggregate name is needed for identifying snapshots stream name associated to this
        aggregate version.
        If the aggregate has major changes, then change this version.

        This is just an aggregate version! The id of the object will be in the stream ID!
        I.e., if you change how the aggregator applies events, then please change it. It will then
        start fetching from position 0, and will create new snapshots for this new version.
        """
        return cls.__name__
