#!/bin/sh
set -e

# ---------- 必填参数校验 ----------

if [ -z "$DOMAINS" ]; then
    echo "[ERROR] 未设置环境变量 DOMAINS，请通过 -e DOMAINS='example.com *.example.com' 指定域名。"
    exit 1
fi

if [ -z "$CERTBOT_EMAIL" ]; then
    echo "[ERROR] 未设置环境变量 CERTBOT_EMAIL，请通过 -e CERTBOT_EMAIL='you@example.com' 指定邮箱。"
    exit 1
fi

# ---------- 凭证校验（三选一）----------
# 优先级：环境变量 > CREDENTIALS_FILE 指定文件 > 默认路径 ~/.tcc.ini

if [ -n "$TENCENTCLOUD_SECRET_ID" ] && [ -n "$TENCENTCLOUD_SECRET_KEY" ]; then
    echo "[INFO] 使用环境变量中的腾讯云凭证。"
    CREDENTIALS_ARGS=""
elif [ -n "$CREDENTIALS_FILE" ]; then
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        echo "[ERROR] 凭证文件 '$CREDENTIALS_FILE' 不存在，请通过 -v /path/to/tcc.ini:$CREDENTIALS_FILE 挂载。"
        exit 1
    fi
    echo "[INFO] 使用凭证文件：$CREDENTIALS_FILE"
    CREDENTIALS_ARGS="--certbot-tcc-credentials $CREDENTIALS_FILE"
elif [ -f "$HOME/.tcc.ini" ]; then
    echo "[INFO] 使用默认凭证文件：$HOME/.tcc.ini"
    CREDENTIALS_ARGS=""
else
    echo "[ERROR] 未找到任何凭证。请通过以下任一方式提供："
    echo "  1. 环境变量：TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY"
    echo "  2. 挂载凭证文件并设置 CREDENTIALS_FILE=/tcc.ini"
    echo "  3. 将凭证文件放置于 $HOME/.tcc.ini"
    exit 1
fi

# ---------- 构造 certbot 域名参数（将空格分隔的域名转换为多个 -d 参数）----------

DOMAIN_ARGS=""
for d in $DOMAINS; do
    DOMAIN_ARGS="$DOMAIN_ARGS -d $d"
done

# ---------- 执行证书申请 ----------

echo "[INFO] 开始申请证书，域名：$DOMAINS"

certbot certonly \
    --authenticator certbot-tcc \
    --certbot-tcc-propagation-seconds "${PROPAGATION_SECONDS:-10}" \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --non-interactive \
    $CREDENTIALS_ARGS \
    $DOMAIN_ARGS

echo "[INFO] 证书申请完成，容器退出。"
