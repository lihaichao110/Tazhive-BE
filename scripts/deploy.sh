#!/usr/bin/env bash

set -Eeuo pipefail

# 本脚本由 GitHub Actions 在服务器上调用，唯一参数为 commit SHA 对应的完整镜像名。
readonly TARGET_IMAGE="${1:?用法: deploy.sh <ghcr-image:commit-sha>}"
readonly DEPLOY_DIR="${DEPLOY_DIR:-/opt/taiwishub}"
readonly COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.yml"
readonly ENV_FILE="${DEPLOY_DIR}/.env"
readonly STATE_FILE="${DEPLOY_DIR}/.deployed-image"
readonly LOCK_FILE="${DEPLOY_DIR}/.deploy.lock"

if [[ ! "$TARGET_IMAGE" =~ ^ghcr\.io/lihaichao110/tazhive-be:[0-9a-f]{40}$ ]]; then
    echo "拒绝部署非预期镜像: ${TARGET_IMAGE}" >&2
    exit 2
fi

for command_name in docker flock; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "服务器缺少命令: ${command_name}" >&2
        exit 2
    fi
done

if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
    echo "缺少 ${COMPOSE_FILE} 或 ${ENV_FILE}" >&2
    exit 2
fi

cd "$DEPLOY_DIR"
umask 077

# GitHub 侧与服务器侧同时加锁，防止人工发布和自动发布互相覆盖。
exec 9>"$LOCK_FILE"
if ! flock -w 300 9; then
    echo "等待其他部署结束超时" >&2
    exit 1
fi

export APP_IMAGE="$TARGET_IMAGE"
docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" config --quiet

previous_image=""
if [[ -s "$STATE_FILE" ]]; then
    previous_image="$(<"$STATE_FILE")"
else
    current_container="$(docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" ps -q app 2>/dev/null || true)"
    if [[ -n "$current_container" ]]; then
        previous_image="$(docker inspect --format '{{.Config.Image}}' "$current_container")"
    fi
fi

wait_until_healthy() {
    local container_id=""
    local health_status=""

    for _ in {1..45}; do
        container_id="$(docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" ps -q app 2>/dev/null || true)"
        if [[ -n "$container_id" ]]; then
            health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_id" 2>/dev/null || true)"
            case "$health_status" in
                healthy)
                    return 0
                    ;;
                unhealthy|missing)
                    return 1
                    ;;
            esac
        fi
        sleep 2
    done

    return 1
}

rollback() {
    if [[ -z "$previous_image" || "$previous_image" == "$TARGET_IMAGE" ]]; then
        echo "没有可回滚的上一版本，移除未通过健康检查的新容器" >&2
        docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" rm --stop --force app || true
        return 1
    fi

    echo "部署失败，回滚到 ${previous_image}" >&2
    export APP_IMAGE="$previous_image"
    docker image inspect "$previous_image" >/dev/null 2>&1 || docker pull "$previous_image"
    docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" up --detach --no-deps --force-recreate app
    wait_until_healthy
}

echo "拉取镜像 ${TARGET_IMAGE}"
docker pull "$TARGET_IMAGE"

# 迁移使用新镜像，但此时旧应用仍在运行；迁移失败不会切换线上容器。
echo "执行数据库迁移"
docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm --no-deps app alembic upgrade head

echo "切换应用容器"
if ! docker compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" up --detach --no-deps --force-recreate app; then
    rollback || echo "容器切换失败，自动回滚也未能恢复服务，请立即人工检查" >&2
    exit 1
fi

if ! wait_until_healthy; then
    rollback || echo "自动回滚未能恢复健康服务，请立即人工检查" >&2
    exit 1
fi

state_temp="$(mktemp "${STATE_FILE}.tmp.XXXXXX")"
printf '%s\n' "$TARGET_IMAGE" > "$state_temp"
mv "$state_temp" "$STATE_FILE"

echo "部署成功: ${TARGET_IMAGE}"
