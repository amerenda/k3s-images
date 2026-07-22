# Vendored from koreader/koreader-sync-server (master), pinned at commit
# 597e0648be0894c535a222f192d7bd583fb3b2dc (2026-05-16). Source lives in
# ./src, vendored directly (rather than a build-time git clone) so the two
# patches below are easy to review/re-apply and the build doesn't depend on
# github.com/koreader being reachable from the arc-runner.
#
# IMPORTANT: base image is the official prebuilt openresty/openresty, not
# upstream's own approach of compiling OpenResty from source on top of
# debian:trixie-slim. The from-source build (nginx + LuaJIT + PCRE + OpenSSL,
# ./configure && make && make install) is the dominant cost of this image
# and took ~50 minutes per multi-arch (amd64+arm64) build in CI — most of
# that under QEMU emulation for the arm64 leg, which is much slower per CPU
# cycle than native compilation. openresty/openresty ships prebuilt,
# real multi-arch (amd64+arm64) manifests via apt, so this cuts the build
# down to just the gin/luarocks steps. Do not switch back to compiling
# OpenResty from source without a real reason.
#
# Patches applied vs. upstream, both in ./src:
#   - db/redis.lua: production block reads REDIS_HOST/REDIS_PORT/REDIS_DB/
#     REDIS_PASSWORD from the environment (falls back to upstream's hardcoded
#     defaults) and calls red:auth() when a password is set. Lets this image
#     point at an external Redis instead of the one upstream bundles.
#   - This Dockerfile drops the bundled `redis-server` package and its runit
#     service (see below) — nothing in this deployment should run a second,
#     unused Redis in the pod.
#
# config/nginx.conf also whitelists REDIS_HOST/REDIS_PORT/REDIS_DB/
# REDIS_PASSWORD via the `env` directive — nginx strips all but explicitly
# whitelisted vars from worker process environments, so without this the
# Lua code's os.getenv() calls silently see nothing.
FROM openresty/openresty:1.31.1.1-bookworm

# install system dependencies (upstream also installs redis-server and a
# pile of nginx/openresty build deps here; dropped both — this image talks
# to an external Redis, see db/redis.lua, and OpenResty is prebuilt above).
# build-essential + libssl-dev are still needed: luasec (installed below)
# compiles a C extension against OpenSSL.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates curl \
        build-essential git openssl libssl-dev \
        luarocks unzip \
        runit \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

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
