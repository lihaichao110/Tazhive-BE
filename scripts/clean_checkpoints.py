"""清理过期的 LangGraph PostgreSQL checkpoint 数据。"""

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.services.database import engine


def clean_checkpoints(days: int = 7) -> int:
    """删除指定天数以前的 checkpoint，并清理对应写入及孤立 blob。"""
    if days < 0:
        raise ValueError("days 不能小于 0")
    if engine.dialect.name != "postgresql":
        raise RuntimeError("checkpoint 清理脚本目前仅支持 PostgreSQL")

    cutoff = datetime.now(UTC) - timedelta(days=days)
    with engine.begin() as conn:
        # checkpoint 的创建时间保存在 JSONB 载荷的 ts 字段中，表本身没有 created_at 列。
        conn.execute(
            text(
                """
                DELETE FROM checkpoint_writes AS writes
                USING checkpoints AS checkpoints
                WHERE writes.thread_id = checkpoints.thread_id
                  AND writes.checkpoint_ns = checkpoints.checkpoint_ns
                  AND writes.checkpoint_id = checkpoints.checkpoint_id
                  AND (checkpoints.checkpoint ->> 'ts')::timestamptz < :cutoff
                """
            ),
            {"cutoff": cutoff},
        )
        result = conn.execute(
            text(
                """
                DELETE FROM checkpoints
                WHERE (checkpoint ->> 'ts')::timestamptz < :cutoff
                """
            ),
            {"cutoff": cutoff},
        )
        # blob 以 channel/version 复用；仅删除已不被任何保留 checkpoint 引用的记录。
        conn.execute(
            text(
                """
                DELETE FROM checkpoint_blobs AS blobs
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM checkpoints
                    WHERE checkpoints.thread_id = blobs.thread_id
                      AND checkpoints.checkpoint_ns = blobs.checkpoint_ns
                      AND checkpoints.checkpoint -> 'channel_versions' ->> blobs.channel
                          = blobs.version
                )
                """
            )
        )

        deleted_count = result.rowcount
        print(f"已删除 {deleted_count} 条过期 checkpoint 记录。")
        return deleted_count


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    clean_checkpoints(days)
