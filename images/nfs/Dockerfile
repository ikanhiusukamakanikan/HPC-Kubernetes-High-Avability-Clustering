FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends nfs-ganesha nfs-ganesha-vfs \
    && rm -rf /var/lib/apt/lists/* && mkdir -p /export /run/ganesha /var/lib/nfs/ganesha
EXPOSE 2049/tcp
CMD ["ganesha.nfsd", "-F", "-L", "/dev/stdout", "-f", "/etc/ganesha/ganesha.conf"]
