FROM python:3.11-slim

WORKDIR /app

# 通过 Git URL 安装插件，@后指定 tag/branch/commit，其余依赖使用腾讯云 PyPI 镜像源
ARG TCC_VERSION=v1.0.0
RUN pip install --no-cache-dir \
    -i https://mirrors.tencent.com/pypi/simple/ \
    "git+https://git.woa.com/lideding/certbot-tcc.git@${TCC_VERSION}"

# 证书输出目录（挂载宿主机目录以持久化证书）
VOLUME ["/etc/letsencrypt", "/var/log/letsencrypt"]

# 凭证文件由运行时通过 -v 挂载进容器
# 使用环境变量传入域名，支持多域名（空格分隔）
ENV DOMAINS=""
ENV CREDENTIALS_FILE="/tcc.ini"
ENV PROPAGATION_SECONDS="10"
ENV CERTBOT_EMAIL=""

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
