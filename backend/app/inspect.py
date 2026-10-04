"""巡检命令行入口：python -m app.inspect [location_id]

退出码：
  0  对账成功（待补/满仓/超占与当场补货单同一套数）
  2  点位不存在
  3  超占道被算进满仓数（满仓/超占桶混用，与 2 互斥、不混用）

巡检全程只读，不会新增或改写任何补货单。
"""
from __future__ import annotations

import sys

from app.database import SessionLocal
from app.services.inspection import (
    InspectionConsistencyError,
    LocationNotFoundError,
    inspect_location,
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    location_id = int(args[0]) if args else 1

    db = SessionLocal()
    try:
        try:
            report = inspect_location(db, location_id)
        except LocationNotFoundError:
            print(f"点位不存在: location_id={location_id}", file=sys.stderr)
            return 2
        except InspectionConsistencyError as exc:
            print(f"巡检对账失败（超占混入满仓）: {exc}", file=sys.stderr)
            return 3

        print(
            f"点位 {location_id} 巡检对账成功: "
            f"待补件数={report['total_fill']} "
            f"满仓道数={report['full_count']} "
            f"超占道数={report['overbooked_count']} "
            f"待补货道={report['need_fill_count']}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
