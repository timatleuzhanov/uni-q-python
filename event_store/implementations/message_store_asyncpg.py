import asyncio
from asyncio.events import AbstractEventLoop
from functools import partial
from typing import Any, AsyncIterable, Callable, Optional, Tuple, cast
from uuid import UUID, uuid4

import asyncpg
import pendulum
import simplejson  # type: ignore[import]
from asyncpg.exceptions import InterfaceError
from asyncpg.pool import Pool
from asyncpg.protocol import Record

from event_store.message import Message
from event_store.message_store import (
    InterfaceNotConnectedError,
    MessageStore,
    UniqueViolationError,
    WrongExpectedVersion,
)
from event_store.types import JSON


# Класс `_PgMessageDbProcs` инкапсулирует связанную бизнес-логику.
class _PgMessageDbProcs:
    acquire_lock = "SELECT acquire_lock($1);"
    write_message = "SELECT write_message($1, $2, $3, $4, $5, $6);"
    get_stream_version = "SELECT stream_version($1);"
    get_stream_messages = "SELECT get_stream_messages($1, $2, $3, $4);"
    get_last_stream_message = "SELECT get_last_stream_message($1);"
    get_category_messages = "SELECT get_category_messages($1, $2, $3, $4, $5, $6, $7)"
    get_version = "SELECT message_store_version();"


# Класс `MessageStoreAsyncpg` инкапсулирует связанную бизнес-логику.
class MessageStoreAsyncpg(MessageStore):
    # Функция `__init__` реализует локальную часть бизнес-логики модуля.
    def __init__(
        self,
        dsn: str,
        loop: Optional[AbstractEventLoop] = None,
        json_dumps: Optional[Callable[[Any], str]] = None,
        json_loads: Optional[Callable[[str], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._loop: Optional[AbstractEventLoop]
        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._dsn = dsn
        self._config = dict(**kwargs)
        self._pool: Optional[Pool] = None
        self._json_dumps = json_dumps or partial(simplejson.dumps, use_decimal=True)
        self._json_loads = json_loads or partial(simplejson.loads, use_decimal=True)

    @classmethod
    # Функция `from_uri` реализует локальную часть бизнес-логики модуля.
    def from_uri(cls, uri: str) -> "MessageStoreAsyncpg":
        psycopg_prefix = "postgresql+psycopg2"
        if uri.startswith(psycopg_prefix):
            uri = "postgresql" + uri[len(psycopg_prefix) :]
        return cls(dsn=uri)

    @property
    # Функция `_connected` реализует локальную часть бизнес-логики модуля.
    def _connected(self) -> bool:
        return self._pool is not None and not self._pool._closed

    # Функция `_require_connection` реализует локальную часть бизнес-логики модуля.
    def _require_connection(self) -> None:
        if not self._connected:
            raise InterfaceNotConnectedError()

    # Функция `_msg_from_record` реализует локальную часть бизнес-логики модуля.
    def _msg_from_record(self, record: Record) -> Message:
        return Message(
            stream=record["stream_name"],
            type=record["type"],
            data=self._json_loads(record["data"]),
            id=UUID(record["id"]),
            metadata=self._json_loads(record["metadata"]) if record["metadata"] else {},
            position=int(record["position"]),
            global_position=int(record["global_position"]),
            time=pendulum.instance(record["time"], "UTC"),
        )

    async def start(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                loop=self._loop,
                server_settings={"search_path": "message_store, public"},
                **self._config,
            )

        # setup json serialization
        async with self._pool.acquire() as conn:
            await conn.set_type_codec(
                "json",
                encoder=self._json_dumps,
                decoder=self._json_loads,
                schema="pg_catalog",
            )

    async def stop(self) -> None:
        self._require_connection()
        await cast(Pool, self._pool).close()
        self._pool = None

    async def acquire_lock(self, stream: str) -> int:
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                result = (await conn.fetchrow(_PgMessageDbProcs.acquire_lock, stream))[0]
                return int(result)
        except InterfaceError:
            raise InterfaceNotConnectedError()

    async def get_message_store_version(self) -> Tuple[int, ...]:
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                res = await conn.fetchrow(_PgMessageDbProcs.get_version)
                if not res:
                    return 0, 0
                return tuple(map(int, res[0].split(".")))
        except InterfaceError:
            raise InterfaceNotConnectedError()

    async def write_message(
        self,
        stream: str,
        type_: str,
        data: Optional[JSON] = None,
        metadata: Optional[JSON] = None,
        id_: Optional[UUID] = None,
        expected_version: Optional[int] = None,
    ) -> Message:
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                id_ = id_ or uuid4()
                data = data or {}
                try:
                    result = (
                        await conn.fetchrow(
                            _PgMessageDbProcs.write_message,
                            str(id_),
                            stream,
                            type_,
                            self._json_dumps(data),
                            self._json_dumps(metadata) if metadata else None,
                            expected_version,
                        )
                    )[0]
                    position = result or 0
                    return Message(
                        stream=stream,
                        type=type_,
                        data=data,
                        id=id_,
                        metadata=(metadata or {}),
                        position=position,
                    )
                except Exception as e:
                    if isinstance(e, asyncpg.exceptions.RaiseError):
                        if "wrong expected version" in str(e).lower():
                            raise WrongExpectedVersion()
                        raise e
                    elif isinstance(e, asyncpg.exceptions.UniqueViolationError):
                        raise UniqueViolationError()
                    else:
                        raise e
        except InterfaceError:
            raise InterfaceNotConnectedError()

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
        args = (
            category,
            max(0, global_position),
            max(1, batch_size),
            correlation,
            consumer_group_member,
            consumer_group_size,
            sql_condition,
        )
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                async with conn.transaction():
                    async for res in conn.cursor(
                        _PgMessageDbProcs.get_category_messages, *args
                    ):
                        yield self._msg_from_record(res[0])
        except InterfaceError:
            raise InterfaceNotConnectedError()

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
        args = (
            stream,
            max(0, position),
            max(1, batch_size),
            sql_condition,
        )
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                async with conn.transaction():
                    async for res in conn.cursor(
                        _PgMessageDbProcs.get_stream_messages, *args
                    ):
                        yield self._msg_from_record(res[0])
        except InterfaceError:
            raise InterfaceNotConnectedError()

    async def _get_last_stream_message(self, stream: str) -> Optional[Message]:
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                res = await conn.fetchrow(
                    _PgMessageDbProcs.get_last_stream_message, stream
                )
                if res is None:
                    return None
                res_dict = dict(res[0])
                if not res_dict:
                    return None
                return self._msg_from_record(res_dict)
        except InterfaceError:
            raise InterfaceNotConnectedError()

    async def get_stream_version(self, stream: str) -> int:
        self._require_connection()
        try:
            async with cast(Pool, self._pool).acquire() as conn:
                result = (
                    await conn.fetchrow(_PgMessageDbProcs.get_stream_version, stream)
                )[0]
                if result is None:
                    return -1
                return int(result)
        except InterfaceError:
            raise InterfaceNotConnectedError()
