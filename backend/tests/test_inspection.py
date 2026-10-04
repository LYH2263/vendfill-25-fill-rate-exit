"""只读巡检入口验收：

- 与当场补货单同一套数，且巡检本身不落单、不改写已存单据
- 点位不存在 -> CLI 退出 2（HTTP 404）
- 超占道算进满仓 -> CLI 退出 3，且与 2 互斥不混用
- 种子 C2 口香糖必须是超占，不算满仓
- 改库存后再巡检吃新库存，不吃进程旧计数
"""

from app.models.models import Lane, RefillOrder
from app.services import inspection as inspection_svc
from app.inspect import main as cli_main


def _line_by_slot(report, slot_no: str) -> dict:
    return next(l for l in report["lines"] if l["slot_no"] == slot_no)


def test_seed_gum_lane_is_overbooked_not_full(client):
    """种子里 C2 口香糖(容量24/库存24/在途2)必须报超占，满仓侧不含它。"""
    r = client.get("/api/inspection?location_id=1")
    assert r.status_code == 200
    report = r.json()
    gum = _line_by_slot(report, "C2")
    assert gum["sku_name"] == "口香糖"
    assert gum["status"] == "overbooked"
    assert gum["gap"] == -2
    assert gum["fill_qty"] == 0

    full_slots = [l["slot_no"] for l in report["lines"] if l["status"] == "full"]
    assert "C2" not in full_slots
    assert report["overbooked_count"] == 1
    # 种子里只有 A2(可乐 18/18/0) 与 B2(巧克力 10+5=15) 满仓
    assert sorted(full_slots) == ["A2", "B2"]
    assert report["full_count"] == 2
    # 待补件数：A1=15, B1=7, C1=10  => 32
    assert report["total_fill"] == 32
    assert report["need_fill_count"] == 3


def test_inspection_matches_on_the_fly_refill_order(client):
    """巡检数与当场生成的补货单完全对得上。"""
    insp = client.get("/api/inspection?location_id=1").json()
    order = client.post("/api/refills/run?location_id=1").json()
    for key in ("total_fill", "need_fill_count", "full_count", "overbooked_count"):
        assert insp[key] == order[key]
    assert [(l["lane_id"], l["gap"], l["fill_qty"], l["status"]) for l in insp["lines"]] == \
           [(l["lane_id"], l["gap"], l["fill_qty"], l["status"]) for l in order["lines"]]


def test_inspection_creates_no_order_before_and_after(client, db_engine):
    """对账前后巡检自己不得增加补货单数量（尤其无单时不能偷偷落一张）。"""
    _engine, TestSession = db_engine

    def count_orders() -> int:
        db = TestSession()
        try:
            return db.query(RefillOrder).count()
        finally:
            db.close()

    assert count_orders() == 0  # 前置：无任何补货单
    r1 = client.get("/api/inspection?location_id=1")
    assert r1.status_code == 200
    assert count_orders() == 0  # 巡检不得借 latest 之类入口落单

    saved = client.post("/api/refills/run?location_id=1").json()
    assert count_orders() == 1
    r2 = client.get("/api/inspection?location_id=1")
    assert r2.status_code == 200
    assert count_orders() == 1  # 对账后仍不得新增
    r3 = client.get("/api/inspection?location_id=1")
    assert r3.status_code == 200
    assert count_orders() == 1  # 反复巡检也不落单


def test_inspection_does_not_rewrite_saved_order(client, db_engine):
    """巡检不得改写先前生成并保存下来的补货单。"""
    _engine, TestSession = db_engine
    saved = client.post("/api/refills/run?location_id=1").json()

    db = TestSession()
    try:
        order = db.get(RefillOrder, saved["id"])
        snapshot = order.lines_json
        created_at = order.created_at
    finally:
        db.close()

    client.get("/api/inspection?location_id=1")
    client.get("/api/inspection?location_id=1")

    db = TestSession()
    try:
        order = db.get(RefillOrder, saved["id"])
        assert order.lines_json == snapshot  # 内容原样
        assert order.created_at == created_at
    finally:
        db.close()


def test_inspection_reflects_updated_stock_not_stale_counters(client, db_engine):
    """改库存后再巡检必须吃新库存，禁止吃进程里旧计数。"""
    _engine, TestSession = db_engine
    first = client.get("/api/inspection?location_id=1").json()
    assert _line_by_slot(first, "A1")["gap"] == 15

    # 直接在另一个会话/请求之外把库存改满
    db = TestSession()
    try:
        a1 = db.query(Lane).filter(Lane.slot_no == "A1").one()
        a1.stock = 20
        db.commit()
    finally:
        db.close()

    second = client.get("/api/inspection?location_id=1").json()
    a1 = _line_by_slot(second, "A1")
    assert a1["stock"] == 20
    assert a1["gap"] == 0
    assert a1["status"] == "full"
    assert second["full_count"] == first["full_count"] + 1
    assert second["total_fill"] == first["total_fill"] - 15


def test_missing_location_http_404_and_cli_exit_2(client, monkeypatch, db_engine):
    """点位不存在：HTTP 404，CLI 退出 2。"""
    r = client.get("/api/inspection?location_id=999")
    assert r.status_code == 404

    _engine, TestSession = db_engine
    monkeypatch.setattr(inspection_svc, "SessionLocal", TestSession, raising=False)
    import app.inspect as inspect_mod
    monkeypatch.setattr(inspect_mod, "SessionLocal", TestSession)
    assert cli_main(["999"]) == 2


def test_overbooked_counted_as_full_is_exit_3_not_2(client, monkeypatch, db_engine):
    """有点位却把超占道算进满仓数 -> 退出 3；与退出 2 严格分开、不得混用。"""
    import app.inspect as inspect_mod
    _engine, TestSession = db_engine
    monkeypatch.setattr(inspect_mod, "SessionLocal", TestSession)

    # 真实点位(1)存在，但人为制造“满仓桶把超占道也收进去”的缺陷
    def broken_summarize(lines):
        good = {l.lane_id: l for l in lines}
        return {
            "total_fill": sum(l.fill_qty for l in lines),
            "need_fill_count": sum(1 for l in lines if l.status == "need_fill"),
            # 缺陷复现：把 gap < 0 的超占道也并进满仓计数
            "full_count": sum(1 for l in lines if l.gap <= 0),
            "overbooked_count": sum(1 for l in lines if l.status == "overbooked"),
            "lines": [
                {**l.__dict__, "status": "full"} if l.gap < 0 else l.__dict__
                for l in lines
            ],
        }

    monkeypatch.setattr(inspection_svc, "summarize", broken_summarize)
    # 点位确实存在：绝不能报 2
    assert cli_main(["1"]) == 3


def test_successful_reconciliation_cli_exit_0(client, monkeypatch, db_engine):
    """对账成功退出 0。"""
    import app.inspect as inspect_mod
    _engine, TestSession = db_engine
    monkeypatch.setattr(inspect_mod, "SessionLocal", TestSession)
    assert cli_main(["1"]) == 0


def test_service_is_readonly_against_session(client, db_engine):
    """服务层直测：巡检不产生任何待写改动。"""
    _engine, TestSession = db_engine
    db = TestSession()
    try:
        report = inspection_svc.inspect_location(db, 1)
        assert report["overbooked_count"] == 1
        # 巡检过程中会话内不应出现新增/脏对象
        assert not db.new
        assert not db.dirty
    finally:
        db.close()


def test_service_missing_location_raises_not_found(db_engine):
    _engine, TestSession = db_engine
    db = TestSession()
    try:
        try:
            inspection_svc.inspect_location(db, 999)
        except inspection_svc.LocationNotFoundError:
            pass
        else:
            raise AssertionError("点位不存在应抛 LocationNotFoundError")
    finally:
        db.close()
