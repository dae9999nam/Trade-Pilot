from typing import Any

import pytest

from config import settings
from creon_client import (
    CreonClient,
    CreonConfigurationError,
    CreonOrderNotFoundError,
    CreonOrderRejectedError,
)


def order_row(
    *,
    order_number: int = 1001,
    original_order_number: int = 0,
    quantity: int = 10,
    filled: int = 0,
    confirmed: int = 0,
    cancelable: int | None = None,
    amend_cancel_code: str = "1",
    rejection: str = "",
) -> dict[int, Any]:
    return {
        1: order_number,
        2: original_order_number,
        3: "005930",
        4: "Samsung Electronics",
        7: quantity,
        8: 70000,
        9: filled,
        10: 0,
        12: confirmed,
        13: "cancel" if amend_cancel_code == "3" else "normal",
        14: rejection,
        22: cancelable,
        28: "",
        35: "2",
        36: amend_cancel_code,
        41: "K",
    }


def test_order_records_from_5341_maps_official_fields() -> None:
    client = CreonClient()
    dib = FakeDib(
        rows=[
            {
                1: 1001,
                2: 0,
                3: "005930",
                4: "Samsung Electronics",
                7: 10,
                8: 70000,
                9: 4,
                10: 2,
                12: 0,
                13: "normal",
                14: "",
                22: 6,
                28: "",
                35: "2",
                36: "1",
                41: "K",
            }
        ]
    )

    records = client._order_records_from_5341(dib)

    assert len(records) == 1
    record = records[0]
    assert record.order_number == "1001"
    assert record.original_order_number is None
    assert record.symbol == "A005930"
    assert record.order_quantity == 10
    assert record.total_filled_quantity == 4
    assert record.cancelable_quantity == 6
    assert record.side_code == "2"
    assert record.exchange_code == "K"


@pytest.mark.parametrize(
    ("rows", "expected_status", "expected_filled", "expected_remaining"),
    [
        ([order_row(quantity=10, filled=0, cancelable=10)], "SUBMITTED", 0, 10),
        ([order_row(quantity=10, filled=4, cancelable=6)], "PARTIALLY_FILLED", 4, 6),
        ([order_row(quantity=10, filled=10, cancelable=0)], "FILLED", 10, 0),
        ([order_row(quantity=10, filled=0, cancelable=0, rejection="Insufficient cash")], "REJECTED", 0, 0),
        (
            [
                order_row(quantity=10, filled=3, cancelable=0),
                order_row(
                    order_number=2002,
                    original_order_number=1001,
                    quantity=7,
                    confirmed=7,
                    amend_cancel_code="3",
                ),
            ],
            "CANCELED",
            3,
            0,
        ),
    ],
)
def test_status_from_5341_records(
    rows: list[dict[int, Any]],
    expected_status: str,
    expected_filled: int,
    expected_remaining: int,
) -> None:
    client = CreonClient()
    records = client._order_records_from_5341(FakeDib(rows=rows))

    status = client._status_from_order_records("1001", records)

    assert status.status == expected_status
    assert status.filled_quantity == expected_filled
    assert status.remaining_quantity == expected_remaining
    assert status.raw_payload is not None
    assert status.raw_payload["object"] == "CpTrade.CpTd5341"


def test_status_from_5341_does_not_infer_missing_order_as_filled() -> None:
    client = CreonClient()

    with pytest.raises(CreonOrderNotFoundError):
        client._status_from_order_records("1001", [])


def test_fetch_order_records_uses_all_exchanges_and_per_order_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "creon_account_no", "12345678")
    monkeypatch.setattr(settings, "creon_goods_code", "01")
    history = FakeDib(rows=[order_row()])
    win32com_client = FakeWin32Com({"CpTrade.CpTd5341": history})

    records, page_count = CreonClient()._fetch_order_records_5341(win32com_client)

    assert len(records) == 1
    assert page_count == 1
    assert history.inputs == {
        0: "12345678",
        1: "01",
        2: "",
        3: 0,
        4: ord("1"),
        5: 20,
        6: ord("2"),
        7: ord("0"),
    }


def test_submit_cancel_0314_maps_original_order_and_cancel_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "creon_account_no", "12345678")
    monkeypatch.setattr(settings, "creon_goods_code", "01")
    cancel = FakeDib(rows=[], headers={6: 2002}, message="Accepted")

    cancel_order_id, status_code, message = CreonClient()._submit_cancel_0314(
        cancel,
        "1001",
        "A005930",
    )

    assert cancel.inputs == {
        1: 1001,
        2: "12345678",
        3: "01",
        4: "A005930",
        5: 0,
    }
    assert cancel_order_id == "2002"
    assert status_code == 0
    assert message == "Accepted"
    assert cancel.block_requested


def test_submit_cancel_0314_surfaces_rejection_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "creon_account_no", "12345678")
    cancel = FakeDib(rows=[], status=4, message="Cannot cancel")

    with pytest.raises(CreonOrderRejectedError) as exc_info:
        CreonClient()._submit_cancel_0314(cancel, "1001", "A005930")

    assert exc_info.value.code == "creon_order_cancel_rejected"
    assert not exc_info.value.retryable
    assert exc_info.value.status_code == 409


@pytest.mark.parametrize("value", ["", "ABC", "0", "-1"])
def test_broker_order_id_must_be_positive_numeric(value: str) -> None:
    with pytest.raises(CreonConfigurationError) as exc_info:
        CreonClient()._normalize_broker_order_id(value)

    assert exc_info.value.status_code == 400


class FakeDib:
    Continue = False

    def __init__(
        self,
        rows: list[dict[int, Any]],
        *,
        headers: dict[int, Any] | None = None,
        status: int = 0,
        message: str = "OK",
    ) -> None:
        self.rows = rows
        self.headers = headers or {}
        self.status = status
        self.message = message
        self.inputs: dict[int, Any] = {}
        self.block_requested = False

    def SetInputValue(self, field: int, value: Any) -> None:
        self.inputs[field] = value

    def BlockRequest(self) -> None:
        self.block_requested = True

    def GetDibStatus(self) -> int:
        return self.status

    def GetDibMsg1(self) -> str:
        return self.message

    def GetHeaderValue(self, header: int) -> Any:
        if header == 6 and header not in self.headers:
            return len(self.rows)
        return self.headers.get(header)

    def GetDataValue(self, field: int, row: int) -> Any:
        return self.rows[row].get(field)


class FakeWin32Com:
    def __init__(self, objects: dict[str, Any]) -> None:
        self.objects = objects

    def Dispatch(self, name: str) -> Any:
        return self.objects[name]
