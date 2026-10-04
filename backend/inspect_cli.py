"""只读巡检/对账命令行入口。

用法：python inspect.py [location_id]（默认点位 1）

退出码：
  0  对账成功：巡检数与按当前库存独立复算一致
  2  点位不存在
  3  有点位，但超占道被算进了满仓侧（与 2 互不混用）
  1  其他对账失败

只读：本脚本不生成、不改写任何补货单，也不调用无单时会自动落单的 /refills/latest。
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import Lane, Location
from app.services.inspection import (
    EXIT_LOCATION_MISSING,
    EXIT_OK,
    EXIT_OVERBOOKED_AS_FULL,
    inspect_location,
)


def expected_counts(lanes: list[Lane]) -> tuple[set[int], set[int], int]:
    """不依赖 fill_engine，按原始库存独立复算一份期望值用于对账。"""
    full: set[int] = set()
    overbooked: set[int] = set()
    pending = 0
    for l in lanes:
        gap = l.capacity - l.stock - l.in_transit
        if gap < 0:
            overbooked.add(l.id)
        elif gap == 0:
            full.add(l.id)
        else:
            pending += gap
    return full, overbooked, pending


def reconcile(report: dict, lanes: list[Lane]) -> tuple[int, str]:
    """拿巡检报告与独立复算结果对账，返回 (退出码, 说明)。"""
    exp_full, exp_over, exp_pending = expected_counts(lanes)
    reported_full = set(report["full_lane_ids"])
    reported_over = set(report["overbooked_lane_ids"])

    # 3 优先：有点位却把超占道算进满仓侧。
    leaked = (reported_full & reported_over) or (reported_full & exp_over)
    if leaked or report.get("code") == EXIT_OVERBOOKED_AS_FULL:
        return EXIT_OVERBOOKED_AS_FULL, f"超占道被计入满仓: {sorted(leaked)}"

    if (
        report["pending_fill"] != exp_pending
        or reported_full != exp_full
        or reported_over != exp_over
    ):
        return 1, (
            f"巡检=(待补{report['pending_fill']}, 满仓{len(reported_full)}, "
            f"超占{len(reported_over)}) 复算=(待补{exp_pending}, 满仓{len(exp_full)}, "
            f"超占{len(exp_over)})"
        )
    return EXIT_OK, "巡检数与当前库存口径一致；未生成或修改任何补货单。"


def main(argv: list[str]) -> int:
    location_id = int(argv[1]) if len(argv) > 1 else 1
    # 每次运行都开全新会话，现读数据库，杜绝吃进程里的旧计数。
    db = SessionLocal()
    try:
        if db.get(Location, location_id) is None:
            print(f"[巡检] 点位 {location_id} 不存在", file=sys.stderr)
            return EXIT_LOCATION_MISSING

        report = inspect_location(db, location_id)
        lanes = db.scalars(
            select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)
        ).all()

        print(f"[巡检] 点位 {location_id}（{len(lanes)} 条货道）")
        for l in lanes:
            gap = l.capacity - l.stock - l.in_transit
            tag = "超占" if gap < 0 else "满仓" if gap == 0 else "待补"
            print(f"  {l.slot_no} {l.sku_name}: 库存{l.stock} 在途{l.in_transit} "
                  f"容量{l.capacity} 缺口{gap} [{tag}]")
        print(f"  待补件数: {report['pending_fill']}")
        print(f"  满仓道数: {report['full_count']}")
        print(f"  超占道数: {report['overbooked_count']}")

        code, msg = reconcile(report, lanes)
        if code == EXIT_OK:
            print(f"[对账成功] {msg}")
        else:
            print(f"[对账失败] {msg}", file=sys.stderr)
        return code
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
