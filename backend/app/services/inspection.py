"""只读巡检：按当前库存重算，与补货单同一套数；不落单、不改单、不读进程旧计数。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Lane, Location
from app.services.fill_engine import build_fill_lines, summarize

# 退出码：0 对账成功；2 点位不存在；3 存在超占道混入满仓（2 与 3 互不混用）
EXIT_OK = 0
EXIT_LOCATION_MISSING = 2
EXIT_OVERBOOKED_AS_FULL = 3


def inspect_location(db: Session, location_id: int) -> dict:
    """对指定点位做只读巡检。

    每次都用传入会话从数据库现读货道，再走与生成补货单完全相同的
    build_fill_lines / summarize，保证两边数对得上；函数自身不写库、
    不提交、不触碰 RefillOrder，也不依赖任何进程内缓存计数。
    """
    loc = db.get(Location, location_id)
    if loc is None:
        # 点位不存在：单独退出 2，绝不与 3 混用
        return {
            "code": EXIT_LOCATION_MISSING,
            "location_id": location_id,
            "found": False,
            "pending_fill": 0,
            "total_fill": 0,
            "full_count": 0,
            "overbooked_count": 0,
            "full_lane_ids": [],
            "overbooked_lane_ids": [],
            "lines": [],
        }

    lanes = db.scalars(
        select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)
    ).all()
    payload = [
        {
            "id": l.id,
            "slot_no": l.slot_no,
            "sku_name": l.sku_name,
            "capacity": l.capacity,
            "stock": l.stock,
            "in_transit": l.in_transit,
        }
        for l in lanes
    ]

    lines = build_fill_lines(payload)
    summary = summarize(lines)

    # 满仓（gap==0）与超占（gap<0）由引擎按互斥状态分开，超占道不进满仓侧。
    full_ids = [l.lane_id for l in lines if l.status == "full"]
    overbooked_ids = [l.lane_id for l in lines if l.status == "overbooked"]

    # 独立审计护栏：不看引擎状态，直接按原始库存重算超占道集合。
    # 有点位时若任何超占道出现在满仓侧，退出 3（与点位不存在的 2 互不混用）。
    raw_overbooked_ids = {
        int(l["id"])
        for l in payload
        if int(l["capacity"]) - int(l["stock"]) - int(l["in_transit"]) < 0
    }
    leaked = raw_overbooked_ids & set(full_ids)
    code = EXIT_OVERBOOKED_AS_FULL if leaked else EXIT_OK
    return {
        "code": code,
        "location_id": location_id,
        "found": True,
        "pending_fill": summary["total_fill"],
        "total_fill": summary["total_fill"],
        "need_fill_count": summary["need_fill_count"],
        "full_count": summary["full_count"],
        "overbooked_count": summary["overbooked_count"],
        "full_lane_ids": full_ids,
        "overbooked_lane_ids": overbooked_ids,
        "lines": summary["lines"],
    }
