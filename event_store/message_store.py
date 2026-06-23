import datetime
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterable, Optional, Tuple, Type, TypeVar, cast
from uuid import UUID

from tenacity import retry
from tenacity.retry import retry_if_exception_type
from tenacity.stop import stop_after_attempt
from tenacity.wait import wait_random

from event_store.aggregate import Aggregate
from event_store.message import Message
from event_store.types import JSON


# Класс `WrongExpectedVersion` инкапсулирует связанную бизнес-логику.
class WrongExpectedVersion(Exception):
    pass


# Класс `UniqueViolationError` инкапсулирует связанную бизнес-логику.
class UniqueViolationError(Exception):
    pass


# Класс `InterfaceNotConnectedError` инкапсулирует связанную бизнес-логику.
class InterfaceNotConnectedError(Exception):
    pass


T_Aggregate = TypeVar("T_Aggregate", bound=Aggregate)


# Класс `MessageStore` инкапсулирует связанную бизнес-логику.
class MessageStore(ABC):
    DELIM = "-"  # stream = category + delim + stream-id
    ORIGIN_STREAM_NAME = "originStreamName"

    @asynccontextmanager
    async def started(self) -> AsyncGenerator["MessageStore", None]:
        try:
            await self.start()
            yield self
        finally:
            await self.stop()

    @classmethod
    # Функция `category` реализует локальную часть бизнес-логики модуля.
    def category(cls, stream: str) -> str:
        return stream.split(cls.DELIM)[0]

    @classmethod
    # Функция `is_category` проверяет условие и возвращает булев результат.
    def is_category(cls, stream: str) -> bool:
        return cls.DELIM not in stream

    @classmethod
    # Функция `stream_id` реализует локальную часть бизнес-логики модуля.
    def stream_id(cls, stream: str) -> Optional[str]:
        if cls.DELIM not in stream:
            return None
        return stream.split(cls.DELIM, 1)[1]

    @classmethod
    # Функция `_snapshot_stream_name` реализует локальную часть бизнес-логики модуля.
    def _snapshot_stream_name(cls, stream: str, aggregate: Aggregate) -> str:
        # abc-15D -> abc:snapshot_(get_aggregate_name())-15D
        category = cls.category(stream=stream)
        aggregate_name = aggregate.get_aggregate_name()
        if cls.DELIM in aggregate_name:
            raise ValueError(
                f"Aggregate name ({aggregate_name}) should not contain delimiter: {cls.DELIM}"
            )
        stream_id = cls.stream_id(stream=stream)
        return f"{category}:snapshot_{aggregate_name}{cls.DELIM}{stream_id}"

    @abstractmethod
    async def start(self) -> None:
        pass  # pragma: no cover

    @abstractmethod
    async def stop(self) -> None:
        pass  # pragma: no cover

    @abstractmethod
    async def acquire_lock(self, stream: str) -> int:
        pass  # pragma: no cover

    @abstractmethod
    async def get_message_store_version(self) -> Tuple[int, ...]:
        pass  # pragma: no cover

    @abstractmethod
    async def write_message(
        self,
        stream: str,
        type_: str,
        data: Optional[JSON] = None,
        metadata: Optional[JSON] = None,
        id_: Optional[UUID] = None,
        expected_version: Optional[int] = None,
    ) -> Message:
        pass  # pragma: no cover

    @abstractmethod
    async def get_category_messages(
        self,
        category: str,
        global_position: int = 1,
        batch_size: int = 1000,
        correlation: Optional[str] = None,
        consumer_group_member: Optional[int] = None,
        consumer_group_size: Optional[int] = None,
        sql_condition: Optional[str] = None,
    ) -> AsyncIterable[Message]:
        yield  # type: ignore  # pragma: no cover

    @abstractmethod
    async def get_stream_messages(
        self,
        stream: str,
        position: int = 0,
        batch_size: int = 1000,
        sql_condition: Optional[str] = None,
    ) -> AsyncIterable[Message]:
        """Get messages from a stream.

        Retrieve messages from a single stream, optionally specifying the starting
        position, the number of messages to retrieve, and an additional condition
        that will be appended to the SQL command's WHERE clause.
        """
        yield  # type: ignore  # pragma: no cover

    @abstractmethod
    async def _get_last_stream_message(self, stream: str) -> Optional[Message]:
        pass  # pragma: no cover

    async def get_last_stream_message(self, stream: str) -> Optional[Message]:
        if self.is_category(stream):
            raise ValueError(f"Expected stream, got category ({stream})")
        return await self._get_last_stream_message(stream=stream)

    @abstractmethod
    async def get_stream_version(self, stream: str) -> int:
        pass  # pragma: no cover

    async def fetch(
        self,
        stream: str,  # abc-15D->abc:snapshot_(get_aggregate_name())-15D
        aggregate_class: Type[T_Aggregate],
        batch_size: int = 1000,
        use_snapshots: bool = True,
        global_position: Optional[int] = None,
    ) -> T_Aggregate:
        """Summary:
        1. Read stream messages (with loop, until all)
        2. Apply each message to the aggregate
        3. Return aggregate

        with snapshots:
        1. Try to get the last snapshot (snapshot contains position to N and aggregate data (JSON))
        2. If not found, goto upper use case
        3. Initialize aggregate from JSON snapshot
        4. Read stream messages (with loop, until all) from position N
        5. Apply all these messages to the aggregate
        6. Return aggregate
        """
        if self.is_category(stream):
            raise ValueError(f"Expected stream, got category ({stream})")

        position = 0
        aggregate = aggregate_class.create()
        if global_position is not None:
            use_snapshots = False

        if use_snapshots:
            snapshot_stream_name = self._snapshot_stream_name(
                stream=stream,
                aggregate=aggregate,
            )
            last_snapshot = await self.get_last_stream_message(
                stream=snapshot_stream_name
            )
            if last_snapshot is not None:
                if last_snapshot.type != "snapshot":
                    raise ValueError(
                        f"Not a snapshot (type {last_snapshot.type}) in a snapshot stream: {snapshot_stream_name}"
                    )
                assert "position" in last_snapshot.data
                assert "snapshot" in last_snapshot.data
                assert isinstance(last_snapshot.data["position"], int)
                position = last_snapshot.data["position"] + 1
                snapshot = last_snapshot.data["snapshot"]
                assert snapshot is not None
                aggregate = aggregate.from_json(cast(JSON, snapshot))

        while True:
            messages = [
                message
                async for message in self.get_stream_messages(
                    stream=stream,
                    batch_size=batch_size,
                    position=position,
                )
            ]
            if len(messages) == 0:
                return cast(T_Aggregate, aggregate)
            for message in messages:
                assert isinstance(message.position, int)
                assert message.global_position is not None
                if (
                    global_position is not None
                    and message.global_position > global_position
                ):
                    return cast(T_Aggregate, aggregate)
                aggregate = aggregate.apply(message=message)
                position = message.position + 1

    @retry(  # type: ignore[misc]
        retry=retry_if_exception_type(WrongExpectedVersion),
        stop=stop_after_attempt(3),
        wait=wait_random(min=1, max=3),
    )
    async def write_snapshot(
        self,
        stream: str,
        aggregate_class: Type[Aggregate],
    ) -> None:
        aggregate = await self.fetch(
            stream=stream,
            aggregate_class=aggregate_class,
            use_snapshots=True,
        )
        last_message = await self.get_last_stream_message(stream=stream)
        if last_message is not None:
            if aggregate.position != last_message.position:
                raise WrongExpectedVersion()

            snapshot_stream_name = self._snapshot_stream_name(
                stream=stream,
                aggregate=aggregate,
            )
            assert last_message.position is not None
            data = {
                "position": last_message.position,
                "snapshot": aggregate.to_json(),
            }
            now = datetime.datetime.utcnow()
            await self.write_message(
                stream=snapshot_stream_name,
                data=cast(JSON, data),
                type_="snapshot",
                metadata={
                    "datetime": now.isoformat(),
                },
            )

    async def get_number_of_messages_since_last_snapshot(
        self,
        stream: str,
        aggregate: Aggregate,
    ) -> int:
        snapshot_stream_name = self._snapshot_stream_name(
            stream=stream,
            aggregate=aggregate,
        )
        snapshot_position: int = -1
        last_snapshot = await self.get_last_stream_message(stream=snapshot_stream_name)
        if last_snapshot is not None:
            if last_snapshot.type != "snapshot":
                raise ValueError(
                    f"Not a snapshot (type {last_snapshot.type}) in a snapshot stream: {snapshot_stream_name}"
                )
            assert "position" in last_snapshot.data
            assert isinstance(last_snapshot.data["position"], int)
            snapshot_position = last_snapshot.data["position"]

        last_message_position: int = -1
        last_message = await self.get_last_stream_message(stream=stream)
        if last_message is not None:
            assert last_message.position is not None
            last_message_position = last_message.position

        if last_message_position < snapshot_position:
            raise ValueError(
                f"Wrong snapshot position! (position {snapshot_position} vs "
                f"last message position: {last_message_position})"
            )
        return last_message_position - snapshot_position
