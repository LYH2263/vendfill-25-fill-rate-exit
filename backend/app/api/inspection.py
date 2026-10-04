"""只读巡检 HTTP 入口。

只按当前货道库存出数，不生成补货单、不改写已保存的补货单，
也不调用 /refills/latest（那条入口在无单时会顺手落一张新单）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.inspection import (
    InspectionConsistencyError,
    LocationNotFoundError,
    inspect_location,
)

router = APIRouter(prefix="/inspection", tags=["inspection"])


@router.get("")
def inspect(location_id: int = 1, db: Session = Depends(get_db)):
    try:
        return inspect_location(db, location_id)
    except LocationNotFoundError:
        # 与 /refills/run 一致：点位不存在交由调用方按“退出 2”语义处理（CLI 退出码 2）。
        raise HTTPException(status_code=404, detail="点位不存在")
    except InspectionConsistencyError as exc:
        # 满仓/超占桶混用或口径漂移（CLI 退出码 3），拒绝静默出数。
        raise HTTPException(status_code=409, detail=f"巡检对账失败: {exc}")
