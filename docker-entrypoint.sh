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

# 取第一个域名作为证书目录名（certbot 默认以第一个 -d 的域名命名目录）
PRIMARY_DOMAIN=$(echo "$DOMAINS" | awk '{print $1}')
CERT_FILE="/etc/letsencrypt/live/${PRIMARY_DOMAIN}/fullchain.pem"

# ---------- 申请或续期 ----------

if [ ! -f "$CERT_FILE" ]; then
    # 证书不存在，首次申请
    echo "[INFO] 证书不存在，开始首次申请..."
    certbot certonly \
        --authenticator certbot-tcc \
        --certbot-tcc-propagation-seconds "${PROPAGATION_SECONDS:-10}" \
        --email "$CERTBOT_EMAIL" \
        --agree-tos \
        --non-interactive \
        $CREDENTIALS_ARGS \
        $DOMAIN_ARGS
    echo "[INFO] 证书申请完成，容器退出。"
else
    # 证书已存在，交由 certbot renew 自行判断是否需要续期
    # 默认行为：有效期不足 30 天时才续期，否则跳过并退出
    echo "[INFO] 证书已存在，检查是否需要续期..."
    certbot renew \
        --authenticator certbot-tcc \
        --certbot-tcc-propagation-seconds "${PROPAGATION_SECONDS:-10}" \
        --cert-name "$PRIMARY_DOMAIN" \
        --non-interactive \
        $CREDENTIALS_ARGS
    echo "[INFO] 续期检查完成，容器退出。"
fi
