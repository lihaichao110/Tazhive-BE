"""
导入「在售产品清单」Excel 到数据库 products 表。

用法：
    # 预览解析结果（不写库）
    uv run python scripts/import_products.py --file app/assets/陆家嘴国泰人寿_在售产品清单.xlsx --dry-run

    # 正式导入（按产品名称去重，重复执行不会产生重复数据）
    uv run python scripts/import_products.py --file app/assets/陆家嘴国泰人寿_在售产品清单.xlsx
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# 把项目根目录加入 sys.path，保证无论从哪里执行都能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.logging import logger  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.database import engine  # noqa: E402

# Excel 列名（表头）→ 目标字段 的映射，空单元格统一转 None
COLUMN_MAPPING = {
    "产品名称": "name",
    "产品条款": "terms_url",
    "产品说明文档": "description_url",
    "产品追加保险费规则": "additional_premium_rule_url",
    "产品分类分级": "classification",
}


def read_excel(file_path: str, sheet_name: str | None = None) -> list[dict[str, Any]]:
    """读取 Excel，首行作为表头，返回每行一个 dict（列名 → 单元格值）。"""
    wb = load_workbook(file_path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        logger.warning("Excel 为空或没有表头行")
        wb.close()
        return []

    header = [str(h).strip() if h is not None else "" for h in header]

    records: list[dict[str, Any]] = []
    for row in rows:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue  # 跳过空行
        # 表头和数据列必须一一对应，避免列数异常时静默截断。
        records.append(dict(zip(header, row, strict=True)))

    wb.close()
    return records


def row_to_product(row: dict[str, Any]) -> Product:
    """把一行 Excel 数据映射成 Product 实例，空单元格转 None。"""

    def get(col: str) -> str | None:
        v = row.get(col)
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    return Product(
        name=get("产品名称"),
        terms_url=get("产品条款"),
        description_url=get("产品说明文档"),
        additional_premium_rule_url=get("产品追加保险费规则"),
        classification=get("产品分类分级"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="导入在售产品清单 Excel 到 products 表")
    parser.add_argument("--file", required=True, help="Excel 文件路径")
    parser.add_argument("--sheet", default=None, help="工作表名，默认取第一个 sheet")
    parser.add_argument("--dry-run", action="store_true", help="只解析打印，不写库")
    args = parser.parse_args()

    start = time.perf_counter()
    records = read_excel(args.file, args.sheet)
    logger.info("读取到 %d 行数据（文件：%s）", len(records), args.file)

    if args.dry_run:
        for i, row in enumerate(records, 1):
            logger.info("[dry-run] 第 %d 行：%s", i, row)
        logger.info("dry-run 完成，未写入数据库")
        return

    success, skipped, failed = 0, 0, 0
    with Session(engine) as session:
        # 一次性取出已存在的产品名称，用于幂等去重
        existing_names = set(session.exec(select(Product.name)).all())

        for i, row in enumerate(records, 1):
            try:
                obj = row_to_product(row)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.exception("第 %d 行字段映射失败，已跳过：%s", i, exc)
                continue

            if obj.name in existing_names:
                skipped += 1
                logger.info("第 %d 行产品「%s」已存在，跳过", i, obj.name)
                continue

            session.add(obj)
            existing_names.add(obj.name)
            success += 1

        session.commit()

    elapsed = time.perf_counter() - start
    logger.info(
        "导入完成：成功 %d 条，跳过 %d 条（已存在），失败 %d 条，耗时 %.2fs",
        success,
        skipped,
        failed,
        elapsed,
    )


if __name__ == "__main__":
    main()
