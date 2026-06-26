from decimal import Decimal
from typing import Any

import pytest

from creon_client import CreonClient, CreonRequestError


def test_positions_from_6033_maps_creon_account_rows() -> None:
    client = CreonClient()
    dib = Fake6033Dib(
        rows=[
            {
                0: "Samsung Electronics",
                7: 3,
                9: -71000,
                11: 213000,
                12: "005930",
                15: 2,
                17: "70000.25",
            },
            {
                0: "SK Hynix",
                7: 0,
                9: 130000,
                11: 0,
                12: "A000660",
                15: 0,
                17: 128000,
            },
        ]
    )

    positions = client._positions_from_6033(dib)

    assert len(positions) == 1
    position = positions[0]
    assert position.symbol == "A005930"
    assert position.name == "Samsung Electronics"
    assert position.quantity == 3
    assert position.available_quantity == 2
    assert position.avg_price == Decimal("70000.25")
    assert position.market_price == Decimal("71000")
    assert position.market_value == Decimal("213000")
    assert position.raw_payload is not None
    assert position.raw_payload["fields"]["symbol"] == 12


def test_positions_from_6033_requires_symbol_and_quantity() -> None:
    client = CreonClient()
    dib = Fake6033Dib(rows=[{0: "missing", 7: "", 12: ""}])

    with pytest.raises(CreonRequestError):
        client._positions_from_6033(dib)


class Fake6033Dib:
    def __init__(self, rows: list[dict[int, Any]]) -> None:
        self.rows = rows

    def GetHeaderValue(self, header: int) -> int | None:
        if header == 7:
            return len(self.rows)
        return None

    def GetDataValue(self, field: int, row: int) -> Any:
        return self.rows[row].get(field)
