from decimal import Decimal
from typing import Dict, List, Union

Number = Union[int, float]
JSONFlatTypes = Union[str, int, float, bool, None, Decimal]
# pydantic don't support recursive types so we can reserve few levels of nested objects
JSONTypes = Union[JSONFlatTypes, List[JSONFlatTypes], Dict[str, JSONFlatTypes]]
JSONTypes2 = Union[JSONTypes, List[JSONTypes], Dict[str, JSONTypes]]
JSONTypes3 = Union[JSONTypes2, List[JSONTypes2], Dict[str, JSONTypes2]]
JSON = Dict[str, JSONTypes3]
