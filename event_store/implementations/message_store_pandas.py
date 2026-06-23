from datetime import datetime
from functools import partial
from typing import Any, AsyncIterable, Callable, NamedTuple, Optional, Tuple, Union, cast
from uuid import UUID, uuid4

import pandas
import pandas as pd
import pendulum
import simplejson  # type: ignore[import]

from event_store.message import Message
from event_store.message_store import (
    MessageStore,
    UniqueViolationError,
    WrongExpectedVersion,
)
from event_store.types import JSON


# Класс `PandasRecordNamedTuple` инкапсулирует связанную бизнес-логику.
class PandasRecordNamedTuple(NamedTuple):
    stream: str
    type: str
    data: str
    id: UUID
    metadata: str
    position: int
    global_position: int
    time: datetime


# Класс `MessageStorePandas` инкапсулирует связанную бизнес-логику.
class MessageStorePandas(MessageStore):
    # Функция `__init__` реализует локальную часть бизнес-логики модуля.
    def __init__(
        self,
        json_dumps: Optional[Callable[[Any], str]] = None,
        json_loads: Optional[Callable[[str], Any]] = None,
    ) -> None:
        super().__init__()
        self.events_df = pd.DataFrame(columns=list(PandasRecordNamedTuple._fields))
        self._json_dumps = json_dumps or partial(simplejson.dumps, use_decimal=True)
        self._json_loads = json_loads or partial(simplejson.loads, use_decimal=True)

    # Функция `_msg_from_record` реализует локальную часть бизнес-логики модуля.
    def _msg_from_record(
        self, record: Union[pandas.Series, PandasRecordNamedTuple]
    ) -> Message:
        return Message(
            stream=record.stream,
            type=record.type,
            data=self._json_loads(record.data),
            id=record.id or uuid4(),
            metadata=self._json_loads(record.metadata) if record.metadata else {},
            position=int(record.position),
            global_position=int(record.global_position),
            time=pendulum.instance(record.time, "UTC"),
        )

    async def start(self) -> None:
        pass  # pragma: no cover

    async def stop(self) -> None:
        pass  # pragma: no cover

    async def acquire_lock(self, stream: str) -> int:
        return 0

    async def get_message_store_version(self) -> Tuple[int, ...]:
        return 0, 0, 0

    async def write_message(
        self,
        stream: str,
        type_: str,
        data: Optional[JSON] = None,
        metadata: Optional[JSON] = None,
        id_: Optional[UUID] = None,
        expected_version: Optional[int] = None,
    ) -> Message:
        if len(self.events_df[self.events_df["stream"] == stream]) > 0:
            last_position = self.events_df[self.events_df["stream"] == stream][
                "position"
            ].max()
        else:
            last_position = -1
        if len(self.events_df) > 0:
            last_global_position = self.events_df["global_position"].max()
        else:
            last_global_position = 0
        if (expected_version is not None) and (last_position != expected_version):
            raise WrongExpectedVersion()
        if id_ is None:
            id_ = uuid4()
        if data is None:
            data = {}
        if len(self.events_df[self.events_df["id"] == id_]) > 0:
            raise UniqueViolationError()

        new_row = pd.DataFrame(
            {
                "stream": [stream],
                "type": [type_],
                "data": [self._json_dumps(data)],
                "id": [id_],
                "metadata": [self._json_dumps(metadata) if metadata else None],
                "position": [last_position + 1],
                "global_position": [last_global_position + 1],
                "time": [datetime.now()],
            }
        )
        if self.events_df.empty:
            self.events_df = new_row
        else:
            self.events_df = pd.concat([self.events_df, new_row])
        return self._msg_from_record(new_row.iloc[0])

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
        filtered_df = self.events_df[
            (self.events_df["stream"].str.startswith(f"{category}{self.DELIM}"))
            & (self.events_df["global_position"] >= global_position)
        ]
        # should 'filtered_df' be sorted by 'global_position' field before applying '.head(batch_size)'?
        filtered_df = filtered_df.head(batch_size)
        for row in filtered_df.itertuples():
            yield self._msg_from_record(row)

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
        filtered_df = self.events_df[
            (self.events_df["stream"] == stream)
            & (self.events_df["position"] >= position)
        ]
        # should 'filtered_df' be sorted by 'position' field before applying '.head(batch_size)'?
        filtered_df = filtered_df.head(batch_size)
        for row in filtered_df.itertuples():
            yield self._msg_from_record(row)

    async def _get_last_stream_message(self, stream: str) -> Optional[Message]:
        filtered_df = self.events_df[self.events_df["stream"] == stream]
        if len(filtered_df) == 0:
            return None
        # should 'filtered_df' be sorted by the 'position' field before extracting the last row?
        return self._msg_from_record(filtered_df.iloc[-1])

    async def get_stream_version(self, stream: str) -> int:
        filtered_df = self.events_df[self.events_df["stream"] == stream]
        if len(filtered_df) == 0:
            return -1
        # should 'filtered_df' be sorted by the 'position' field before extracting the last row?
        version = cast(int, self._msg_from_record(filtered_df.iloc[-1]).position)
        return version
