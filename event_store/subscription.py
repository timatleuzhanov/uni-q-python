import asyncio
import logging
from abc import ABC, abstractmethod
from functools import partial
from typing import (
    Any,
    AsyncIterable,
    Callable,
    Coroutine,
    Dict,
    Mapping,
    Optional,
    Type,
    TypeVar,
)

from event_store.message import (
    BuildOptionalTypesFromMessageFactory,
    EventOrCommand,
    Message,
)
from event_store.message_store import MessageStore

logger = logging.getLogger(__name__)


# Класс `Handler` инкапсулирует связанную бизнес-логику.
class Handler(ABC):
    # Функция `__init__` реализует локальную часть бизнес-логики модуля.
    def __init__(self, message_store: MessageStore) -> None:
        self.message_store = message_store
        self._handlers_mapping = self.get_handlers()

    async def handle(self, message: Message) -> None:
        handler = self.get_handler(message=message)
        if not handler:
            return

        await handler(message=message)

    @abstractmethod
    # Функция `get_handlers` получает и возвращает вычисленные/запрошенные данные.
    def get_handlers(self) -> Dict[Any, Callable]:
        raise NotImplementedError

    # Функция `get_handler` получает и возвращает вычисленные/запрошенные данные.
    def get_handler(self, message: Message) -> Optional[Callable]:
        factory = BuildOptionalTypesFromMessageFactory(
            expected_types=set(self._handlers_mapping.keys())
        )
        event = factory.create_from_message(message)
        if type(event) not in self._handlers_mapping:
            return None

        handler = self._handlers_mapping[type(event)]
        return partial(handler, event)


T_EventOrCommand = TypeVar("T_EventOrCommand", bound=EventOrCommand)
HandlersMapping = Mapping[
    Type[T_EventOrCommand],
    Callable[[Message, T_EventOrCommand], Coroutine[Any, Any, None]],
]


# Класс `Subscription` инкапсулирует связанную бизнес-логику.
class Subscription:
    # Функция `__init__` реализует локальную часть бизнес-логики модуля.
    def __init__(
        self,
        message_store: "MessageStore",
        stream_or_category: str,
        handler: Handler,
        subscriber_id: str,
        messages_per_tick: int = 100,
        position_update_interval: int = 100,
        origin_stream_name: Optional[str] = None,
        tick_interval_ms: int = 100,
        async_sleep: Optional[Callable[[float], Any]] = None,
    ):
        self._message_store = message_store
        self._stream_or_category = stream_or_category
        self._handler = handler
        self._subscriber_id = subscriber_id
        self._messages_per_tick = messages_per_tick
        self._position_update_interval = position_update_interval
        self._origin_stream_name = origin_stream_name
        self._tick_interval_ms = tick_interval_ms
        self._current_position = -1
        self._messages_since_last_pos_write = 0
        self._keep_going = False
        self._subscriberStreamName = f"subscriberPosition-{self._subscriber_id}"
        self._is_category = message_store.is_category(stream_or_category)
        self._async_sleep = async_sleep or asyncio.sleep

    # Функция `is_running` проверяет условие и возвращает булев результат.
    def is_running(self) -> bool:
        return self._keep_going

    # Функция `_check_origin_match` реализует локальную часть бизнес-логики модуля.
    def _check_origin_match(self, message: Message) -> bool:
        if self._origin_stream_name is None:
            return True
        if message.metadata is None:
            return False
        if MessageStore.ORIGIN_STREAM_NAME not in message.metadata:
            return False
        message_origin = message.metadata[MessageStore.ORIGIN_STREAM_NAME]
        if message_origin is None:
            return False
        message_origin = str(message_origin)
        if MessageStore.is_category(self._origin_stream_name):
            message_origin = MessageStore.category(message_origin)
        return message_origin == self._origin_stream_name

    async def _get_next_batch_of_messages(self) -> AsyncIterable[Message]:
        starting_position = self._current_position + 1

        if self._is_category:
            next_batch = self._message_store.get_category_messages(
                category=self._stream_or_category,
                batch_size=self._messages_per_tick,
                global_position=starting_position,
            )
        else:
            next_batch = self._message_store.get_stream_messages(
                stream=self._stream_or_category,
                batch_size=self._messages_per_tick,
                position=starting_position,
            )
        async for message in next_batch:
            yield message

    async def tick(self, stop_on_error: bool = False) -> int:
        counter: int = 0
        try:
            next_batch = self._get_next_batch_of_messages()
            messages = [message async for message in next_batch]

            for message in messages:
                assert message is not None
                assert message.global_position is not None
                assert message.position is not None
                if self._check_origin_match(message):
                    await self._handler.handle(message)
                if self._is_category:
                    next_position = message.global_position
                else:
                    next_position = message.position
                await self._update_read_position(position=next_position)
                counter += 1
        except Exception as exception:
            logger.error(
                f"Unexpected error during processing new messages in {self}",
                exc_info=exception,
            )
            if stop_on_error:
                logger.warning(f"Stopping {self}")
                self.stop()
            raise

        return counter

    async def _poll(self) -> None:
        await self._load_position()
        while self._keep_going:
            messages_processed = await self.tick()
            if messages_processed == 0:
                await self._async_sleep(self._tick_interval_ms / 1000)

    async def start(self) -> None:
        logger.info(f'Starting subscription with ID "{self._subscriber_id}"')
        self._keep_going = True
        await self._poll()

    # Функция `stop` реализует локальную часть бизнес-логики модуля.
    def stop(self) -> None:
        self._keep_going = False

    async def _load_position(self) -> None:
        last_message = await self._message_store.get_last_stream_message(
            self._subscriberStreamName
        )
        if last_message is None:
            self._current_position = -1
            return
        assert last_message.data is not None
        assert isinstance(last_message.data["position"], int)
        self._current_position = last_message.data["position"]

    async def _write_position(self, position: int) -> None:
        await self._message_store.write_message(
            stream=self._subscriberStreamName,
            type_="read",
            data={"position": position},
        )

    async def _update_read_position(self, position: int) -> None:
        self._current_position = position
        self._messages_since_last_pos_write += 1
        if self._messages_since_last_pos_write >= self._position_update_interval:
            self._messages_since_last_pos_write = 0
            await self._write_position(position)

    # Функция `__repr__` реализует локальную часть бизнес-логики модуля.
    def __repr__(self) -> str:
        return (
            f'Subscription(stream_or_category="{self._stream_or_category}", '
            f'handler={self._handler}, subscriber_id="{self._subscriber_id}")'
        )

    # Функция `__str__` реализует локальную часть бизнес-логики модуля.
    def __str__(self) -> str:
        return self.__repr__()
