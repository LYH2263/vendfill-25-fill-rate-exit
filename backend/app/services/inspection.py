"""只读巡检：按当前货道库存复算待补/满仓/超占，与当场补货单同一套口径。

与补货单的唯一差别是不落库（RefillOrder）、不碰任何已保存的补货单，
也绝不走 /refills/latest 那条“无单即落单”的入口。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Lane, Location
from app.services.fill_engine import FillLine, build_fill_lines, summarize


class LocationNotFoundError(LookupError):
    """巡检点位不存在（对账退出码 2）。"""


class InspectionConsistencyError(RuntimeError):
    """巡检自对账失败：超占道被混进满仓桶（退出码 3）。"""


def load_lane_payload(db: Session, location_id: int) -> list[dict]:
    """从货道表现读最新库存组装计算入参，不依赖任何进程内旧计数。"""
    return [
        {
            "id": l.id,
            "slot_no": l.slot_no,
            "sku_name": l.sku_name,
            "capacity": l.capacity,
            "stock": l.stock,
            "in_transit": l.in_transit,
        }
        for l in db.scalars(
            select(Lane)
            .where(Lane.location_id == location_id)
            .order_by(Lane.slot_no)
        ).all()
    ]


def inspect_location(db: Session, location_id: int) -> dict:
    """计算巡检结果并自对账。只读：不 add / commit / update 任何对象。

    返回与 fill_engine.summarize 同形的汇总，附带 location_id 与分类桶。
    """
    if db.get(Location, location_id) is None:
        raise LocationNotFoundError(location_id)

    # 独立会话查询，强制吃数据库里的最新库存，而非进程里缓存的旧计数。
    db.expire_all()
    payload = load_lane_payload(db, location_id)
    lines = build_fill_lines(payload)
    summary = summarize(lines)

    _reconcile(lines, summary)

    return {
        "location_id": location_id,
        **summary,
    }


def _reconcile(lines: list[FillLine], summary: dict) -> None:
    """桶不相交校验 + 与引擎汇总的计数独立复算比对。"""
    full_lanes = {l.lane_id for l in lines if l.gap == 0}
    over_lanes = {l.lane_id for l in lines if l.gap < 0}
    if full_lanes & over_lanes:
        raise InspectionConsistencyError(
            f"超占道被算进满仓数: {sorted(full_lanes & over_lanes)}"
        )

    # 注意：满仓桶必须 gap == 0；gap < 0 的超占道只进超占桶。
    full_count = sum(1 for l in lines if l.gap == 0)
    over_count = sum(1 for l in lines if l.gap < 0)
    total_fill = sum(l.gap for l in lines if l.gap > 0)
    if (
        full_count != summary["full_count"]
        or over_count != summary["overbooked_count"]
        or total_fill != summary["total_fill"]
    ):
        # 计数对不上补货单口径：按超占混入满仓的严重性报 3，
        # 其余口径漂移同样拒绝静默出数。
        raise InspectionConsistencyError("巡检与补货单口径不一致")
