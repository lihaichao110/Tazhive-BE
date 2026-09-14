# 生产环境部署

`main` 分支通过检查后，GitHub Actions 会构建 amd64 镜像、推送到 GHCR，并通过 SSH 更新
`agent.lihaichao.cn` 对应的服务器。应用业务密钥只保存在服务器，不经过 GitHub Actions。

## 1. 初始化服务器

服务器需要 Ubuntu、Docker Engine、Docker Compose v2、Nginx、Certbot 和 `flock`。创建部署目录并让部署用户拥有写权限：

```bash
sudo install -d -m 0750 -o <部署用户> -g <部署用户> /opt/taiwishub
```

将 `.env.example` 复制为 `/opt/taiwishub/.env`，至少设置：

```dotenv
DATABASE_URL=postgresql+psycopg://<用户>:<URL编码后的密码>@<数据库地址>:5432/<数据库名>
SECRET_KEY=<足够长的随机字符串>
```

`DATABASE_URL` 指向现有外部 PostgreSQL。数据库应安装 pgvector，且防火墙只允许该应用服务器访问。
可以使用下面的命令生成 JWT 密钥：

```bash
openssl rand -hex 32
```

若 GHCR 包为私有，使用仅有 `read:packages` 权限的 GitHub classic PAT 在服务器完成一次登录：

```bash
docker login ghcr.io -u lihaichao110
```

## 2. 配置 GitHub

在仓库的 `production` Environment 中创建以下 Secrets：

- `PROD_HOST`：服务器 IP 或 SSH 主机名。
- `PROD_USER`：有权运行 Docker、写入 `/opt/taiwishub` 的部署用户。
- `PROD_SSH_PORT`：SSH 端口，例如 `22`。
- `PROD_SSH_PRIVATE_KEY`：部署专用 Ed25519 私钥。
- `PROD_KNOWN_HOSTS`：预先核验过的服务器 host key；不要在 workflow 中临时执行 `ssh-keyscan`。

在可信网络中生成 `PROD_KNOWN_HOSTS` 后，应通过服务器控制台或云厂商页面核对指纹：

```bash
ssh-keyscan -p <SSH端口> -H <服务器地址>
```

## 3. 配置 Nginx 和 HTTPS

把仓库中的配置安装到 Nginx，检查无误后签发证书：

```bash
sudo cp deploy/nginx/agent.lihaichao.cn.conf /etc/nginx/sites-available/agent.lihaichao.cn.conf
sudo ln -s /etc/nginx/sites-available/agent.lihaichao.cn.conf /etc/nginx/sites-enabled/agent.lihaichao.cn.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d agent.lihaichao.cn --redirect
sudo certbot renew --dry-run
```

安全组只开放实际 SSH 端口、80 和 443。应用端口绑定到 `127.0.0.1:8000`，不应额外开放；外部数据库的 5432 也不应对所有公网地址开放。

## 4. 验证和回滚

推送到 `main` 后，在 Actions 页面确认“代码检查与测试”“构建并发布镜像”“部署生产环境”依次成功。然后验证：

```bash
curl -I http://agent.lihaichao.cn/api/v1/health
curl --fail https://agent.lihaichao.cn/api/v1/health
```

部署脚本会等待容器健康，并在失败时自动恢复 `/opt/taiwishub/.deployed-image` 记录的上一镜像。需要人工回滚时，在服务器执行：

```bash
bash /opt/taiwishub/deploy.sh ghcr.io/lihaichao110/tazhive-be:<此前成功的40位提交SHA>
```

数据库迁移发生在应用切换前。迁移必须保持向后兼容；包含删除、重命名等破坏性操作时，应先备份数据库并分阶段发布。
