# nanobot-sandbox:latest
FROM alpine:3.19

# 安装常用工具
RUN apk add --no-cache \
    bash \
    coreutils \
    grep \
    findutils \
    gawk \
    sed \
    git \
    curl \
    wget \
    python3 \
    py3-pip \
    nodejs \
    npm \
    openssh-client \
    ca-certificates \
    && rm -rf /var/cache/apk/*

# 创建非 root 用户
RUN addgroup -g 1000 nanobot && \
    adduser -u 1000 -G nanobot -s /bin/bash -D nanobot

WORKDIR /workspace
USER nanobot

CMD ["/bin/bash"]

# docker build -t nanobot-sandbox:latest -f Dockerfile .