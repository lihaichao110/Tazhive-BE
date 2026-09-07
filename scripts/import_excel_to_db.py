"""
通用 Excel → 数据库 导入脚本模板。

用法：
    # 预览解析结果（不写库）
    uv run python scripts/import_excel_to_db.py --file data.xlsx --dry-run

    # 正式导入
    uv run python scripts/import_excel_to_db.py --file data.xlsx --sheet Sheet1 --batch-size 100

使用前请完成两处
    1. 顶部 import 换成你的目标模型（如 from app.models.agent import Agent）
    2. 在 row_to_model() 里写 Excel 列名 → 模型字段 的映射
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# 把项目根目录加入 sys.path，保证无论从哪里执行都能 import app.*
# （python 运行脚本时 sys.path[0] 是脚本所在目录 scripts/，而非项目根）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.core.logging import logger  # noqa: E402
from app.services.database import engine  # noqa: E402

# from app.models.agent import Agent


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

    # 表头 strip 去除首尾空格，避免列名因空格不匹配
    header = [str(h).strip() if h is not None else "" for h in header]

    records: list[dict[str, Any]] = []
    for row in rows:
        # 跳过整行都是空值的空行
        if row is None or all(v is None or v == "" for v in row):
            continue
        records.append(dict(zip(header, row)))

    wb.close()
    return records


def row_to_model(row: dict[str, Any]):
    """把一行数据转换成目标模型实例 —— 需按你的场景实现。"""
    # return Agent(
    #     name=row.get("名称"),
    #     description=row.get("描述"),
    #     model=row.get("模型", "deepseek-v4-flash"),
    #     temperature=float(row.get("温度", 0.7)),
    # )
    raise NotImplementedError("请在 row_to_model() 中实现 Excel 行 → 模型字段 的映射")


def main() -> None:
    parser = argparse.ArgumentParser(description="读取 Excel 并批量写入数据库")
    parser.add_argument("--file", required=True, help="Excel 文件路径")
    parser.add_argument("--sheet", default=None, help="工作表名，默认取第一个 sheet")
    parser.add_argument("--batch-size", type=int, default=100, help="每批提交条数")
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

    success, failed = 0, 0
    with Session(engine) as session:
        for i, row in enumerate(records, 1):
            try:
                obj = row_to_model(row)
                session.add(obj)
                # 每累计 batch-size 条提交一次，减少事务次数
                if i % args.batch_size == 0:
                    session.commit()
                    logger.info("已提交 %d 条", i)
                success += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.exception("第 %d 行处理失败，已跳过：%s", i, exc)
        # 提交最后不足一批的剩余记录
        if success and success % args.batch_size != 0:
            session.commit()

    elapsed = time.perf_counter() - start
    logger.info("导入完成：成功 %d 条，失败 %d 条，耗时 %.2fs", success, failed, elapsed)


if __name__ == "__main__":
    main()
