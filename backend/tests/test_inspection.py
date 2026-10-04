"""只读巡检与对账退出码测试（SQLite 内存库，不依赖 Postgres）。"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Lane, Location, RefillOrder
from app.services.inspection import (
    EXIT_LOCATION_MISSING,
    EXIT_OK,
    EXIT_OVERBOOKED_AS_FULL,
    inspect_location,
)
from app.services.seed import seed_if_empty
import inspect_cli as inspect_cli_module  # backend/inspect_cli.py

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    seed_if_empty(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def _get_db():
        # 巡检必须每次拿当前会话现读，这里与请求生命周期一致。
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    # 不进入 with 上下文，避免触发 lifespan 去连真实 Postgres；
    # 表结构与种子已由 db fixture 在 SQLite 中就绪。
    yield TestClient(app)
    app.dependency_overrides.clear()


def _gum_lane(db) -> Lane:
    return db.scalar(select(Lane).where(Lane.sku_name == "口香糖"))


# ---------- 种子口径：口香糖必须超占，满仓不含它 ----------

def test_seed_gum_is_overbooked_not_full(db):
    report = inspect_location(db, 1)
    gum = _gum_lane(db)
    assert gum.id in report["overbooked_lane_ids"]
    assert gum.id not in report["full_lane_ids"]
    gum_line = next(l for l in report["lines"] if l["lane_id"] == gum.id)
    assert gum_line["status"] == "overbooked"
    assert report["overbooked_count"] == 1
    # A2 可乐、B2 巧克力满仓；超占的口香糖不得计入
    assert report["full_count"] == 2
    # A1=15, B1=7, C1=10 → 32
    assert report["pending_fill"] == 32
    assert report["code"] == EXIT_OK


# ---------- 只读：巡检前后补货单数量不变 ----------

def test_inspection_creates_no_order(client, db):
    before = db.scalar(select(func.count()).select_from(RefillOrder))
    assert before == 0  # 种子本身不带补货单
    r = client.get("/api/refills/inspection?location_id=1")
    assert r.status_code == 200
    assert r.json()["code"] == 0
    # 连续巡检也不得补落单（不得走无单自动落单的 latest 入口）
    client.get("/api/refills/inspection?location_id=1")
    after = db.scalar(select(func.count()).select_from(RefillOrder))
    assert after == 0


def test_inspection_does_not_touch_latest(client, db, monkeypatch):
    # 显式钉死：巡检请求路径上调用 latest 的自动落单逻辑即视为失败
    import app.api.refills as refills_api

    def _boom(*a, **k):
        raise AssertionError("巡检不得调用会在无单时落单的 latest 入口")

    monkeypatch.setattr(refills_api, "latest", _boom)
    r = client.get("/api/refills/inspection?location_id=1")
    assert r.status_code == 200


# ---------- 巡检数与当场生成的补货单对同一套数 ----------

def test_inspection_matches_freshly_generated_order(client, db):
    run = client.post("/api/refills/run?location_id=1").json()
    insp = client.get("/api/refills/inspection?location_id=1").json()
    assert insp["pending_fill"] == run["total_fill"]
    assert insp["full_count"] == run["full_count"]
    assert insp["overbooked_count"] == run["overbooked_count"]
    assert insp["need_fill_count"] == run["need_fill_count"]
    assert [(l["slot_no"], l["gap"], l["fill_qty"], l["status"]) for l in insp["lines"]] == \
           [(l["slot_no"], l["gap"], l["fill_qty"], l["status"]) for l in run["lines"]]
    # 对账只发生一次 run，巡检不增加单据数量
    assert db.scalar(select(func.count()).select_from(RefillOrder)) == 1


# ---------- 改库存后再巡检必须吃新库存，不吃进程旧计数 ----------

def test_inspection_reflects_updated_stock(db):
    first = inspect_location(db, 1)
    assert first["pending_fill"] == 32

    # 用另一个会话改库存并提交，模拟现场调整
    other = TestingSessionLocal()
    try:
        gum = other.scalar(select(Lane).where(Lane.sku_name == "口香糖"))
        gum.stock = 24
        gum.in_transit = 0  # 消除超占 → 变满仓
        water = other.scalar(select(Lane).where(Lane.sku_name == "矿泉水"))
        water.stock = 20  # 补满 → 少 15 件待补
        other.commit()
    finally:
        other.close()

    fresh = TestingSessionLocal()
    try:
        second = inspect_location(fresh, 1)
        assert second["pending_fill"] == 17  # 32 - 15
        assert second["overbooked_count"] == 0
        assert second["full_count"] == 4  # A1、A2、B2、C2
        # 第一次巡检的旧结果对象不被悄悄改写
        assert first["pending_fill"] == 32
    finally:
        fresh.close()


# ---------- 巡检不得改写已保存的补货单 ----------

def test_inspection_does_not_rewrite_saved_order(client, db):
    run = client.post("/api/refills/run?location_id=1").json()
    order = db.get(RefillOrder, run["id"])
    saved_snapshot = order.lines_json

    # 改库存后巡检：新库存出在巡检里，但旧单据保持落单时的数
    other = TestingSessionLocal()
    try:
        gum = other.scalar(select(Lane).where(Lane.sku_name == "口香糖"))
        gum.stock = 30
        other.commit()
    finally:
        other.close()

    insp = client.get("/api/refills/inspection?location_id=1").json()
    assert insp["overbooked_count"] == 1

    db.expire_all()
    order_after = db.get(RefillOrder, run["id"])
    assert order_after.lines_json == saved_snapshot
    saved = json.loads(saved_snapshot)
    assert saved["total_fill"] == 32


# ---------- 点位不存在 → 2 ----------

def test_missing_location_is_code_2(db):
    report = inspect_location(db, 999)
    assert report["code"] == EXIT_LOCATION_MISSING == 2
    assert report["found"] is False
    # 不存在时不应给出任何像对账成功的计数
    assert report["full_count"] == 0 and report["overbooked_count"] == 0


def test_missing_location_http(client):
    r = client.get("/api/refills/inspection?location_id=999")
    assert r.status_code == 200
    assert r.json()["code"] == 2


# ---------- 超占混入满仓 → 3，且与 2 不混用 ----------

def test_overbooked_leaked_into_full_is_code_3(db):
    report = inspect_location(db, 1)
    lanes = db.scalars(select(Lane).where(Lane.location_id == 1)).all()
    # 正常种子数据不泄漏 → 0
    code, _ = inspect_cli_module.reconcile(report, lanes)
    assert code == 0

    # 人为制造“超占道被算进满仓侧”
    gum = _gum_lane(db)
    bad_report = dict(report)
    bad_report["full_lane_ids"] = report["full_lane_ids"] + [gum.id]
    code, _ = inspect_cli_module.reconcile(bad_report, lanes)
    assert code == EXIT_OVERBOOKED_AS_FULL == 3


def test_codes_2_and_3_never_mix(db):
    missing = inspect_location(db, 999)
    present = inspect_location(db, 1)
    assert missing["code"] == 2 and present["code"] == 0
    # 点位存在才可能出 3；点位不存在只能是 2
    gum = _gum_lane(db)
    lanes = db.scalars(select(Lane).where(Lane.location_id == 1)).all()
    leaked = dict(present)
    leaked["full_lane_ids"] = present["full_lane_ids"] + [gum.id]
    code3, _ = inspect_cli_module.reconcile(leaked, lanes)
    assert code3 == 3 and code3 != missing["code"]


def test_service_guard_code_3_when_engine_misclassifies(db, monkeypatch):
    """引擎若把负缺口道错标成 full，服务层独立审计须直接返回 3。"""
    import app.services.inspection as insp_mod
    real_build = insp_mod.build_fill_lines

    def _tampered(payload, requested=None):
        lines = real_build(payload, requested)
        for l in lines:
            if l.lane_id == _gum_lane(db).id:
                l.status = "full"  # 回归：超占被塞进满仓侧
        return lines

    monkeypatch.setattr(insp_mod, "build_fill_lines", _tampered)
    report = insp_mod.inspect_location(db, 1)
    assert report["code"] == EXIT_OVERBOOKED_AS_FULL == 3
    assert report["full_count"] == 3  # 口香糖被错算进来
    assert report["overbooked_count"] == 0


# ---------- CLI 主入口退出码 ----------

def test_cli_exit_codes(db, monkeypatch):
    monkeypatch.setattr(inspect_cli_module, "SessionLocal", TestingSessionLocal)
    assert inspect_cli_module.main(["inspect.py", "1"]) == 0
    assert inspect_cli_module.main(["inspect.py", "999"]) == 2


def test_cli_is_readonly(db, monkeypatch):
    monkeypatch.setattr(inspect_cli_module, "SessionLocal", TestingSessionLocal)
    inspect_cli_module.main(["inspect.py", "1"])
    assert db.scalar(select(func.count()).select_from(RefillOrder)) == 0
