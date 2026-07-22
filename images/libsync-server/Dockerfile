# Vendored from koreader/koreader-sync-server (master), pinned at commit
# 597e0648be0894c535a222f192d7bd583fb3b2dc (2026-05-16). Source lives in
# ./src, vendored directly (rather than a build-time git clone) so the two
# patches below are easy to review/re-apply and the build doesn't depend on
# github.com/koreader being reachable from the arc-runner.
#
# Patches applied vs. upstream, both in ./src:
#   - db/redis.lua: production block reads REDIS_HOST/REDIS_PORT/REDIS_DB/
#     REDIS_PASSWORD from the environment (falls back to upstream's hardcoded
#     defaults) and calls red:auth() when a password is set. Lets this image
#     point at an external Redis instead of the one upstream bundles.
#   - This Dockerfile drops the bundled `redis-server` package and its runit
#     service (see below) — nothing in this deployment should run a second,
#     unused Redis inside the pod.
FROM debian:trixie-slim

# install system dependencies (upstream also installs redis-server here;
# dropped — this image talks to an external Redis, see db/redis.lua)
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates curl \
        libreadline-dev libncurses5-dev libpcre2-dev libssl-dev \
        build-essential git openssl \
        luarocks unzip \
        zlib1g-dev \
        runit \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ARG OPENRESTY_VER=1.29.2.3
ENV PATH=/opt/openresty/nginx/sbin:$PATH

WORKDIR /app
RUN curl -fL "https://openresty.org/download/openresty-${OPENRESTY_VER}.tar.gz" -o openresty-${OPENRESTY_VER}.tar.gz \
        && tar zxvf openresty-${OPENRESTY_VER}.tar.gz \
        && cd openresty-${OPENRESTY_VER} \
            && ./configure --prefix=/opt/openresty \
            && make && make install \
        && cd .. \
            && rm -rf openresty-${OPENRESTY_VER} openresty-${OPENRESTY_VER}.tar.gz /tmp/*

RUN mkdir -p /etc/nginx/ssl \
    && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/nginx.key -out /etc/nginx/ssl/nginx.crt -subj "/"

# copy only the patch needed for the gin build step
COPY src/gin.patch /tmp/gin.patch

# patch gin for https support
RUN git clone https://github.com/ostinelli/gin \
    && cd gin \
    && patch -N -p1 < /tmp/gin.patch \
    && luarocks make --tree=/usr/local \
    && cd .. \
    && rm -rf gin

# install lua dependencies after gin to avoid gin's pinned old versions overwriting them
RUN luarocks remove --force luasocket 3.0rc1-2 \
    && luarocks install luasocket \
    && luarocks install luasec \
    && luarocks install redis-lua \
    && luarocks install busted \
    && rm -rf /tmp/*

ENV ENABLE_USER_REGISTRATION=true
ENV GIN_ENV=production

# add app source code after so app changes don't invalidate dependency layers
# but before starting the app
COPY src/ koreader-sync-server

# append 'daemon off;' at runtime so tests can still use the config normally
# grep from start of line only; nginx.conf has daemon off commented out by default
RUN mkdir /etc/service/koreader-sync-server \
    && printf "#!/bin/sh\ngrep -q '^daemon off;' /app/koreader-sync-server/config/nginx.conf || echo 'daemon off;' >> /app/koreader-sync-server/config/nginx.conf\ncd /app/koreader-sync-server\nexec gin start" > \
        /etc/service/koreader-sync-server/run \
    && chmod +x /etc/service/koreader-sync-server/run

# 7200: HTTPS with a baked-in self-signed cert (upstream default).
# 17200: plain HTTP, for running behind a TLS-terminating reverse proxy —
# this is what the k3s Ingress uses.
EXPOSE 7200 17200

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD /app/koreader-sync-server/scripts/healthcheck.sh

CMD ["/usr/bin/runsvdir", "-P", "/etc/service"]
