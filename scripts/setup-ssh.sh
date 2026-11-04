#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
HEAD="${CLUSTER_NAME}-control-plane"
docker exec "$HEAD" bash -ceu '
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends openssh-server python3
rm -rf /var/lib/apt/lists/*
if ! id hpc >/dev/null 2>&1; then useradd --create-home --uid 1000 --shell /bin/bash hpc; fi
test "$(id -u hpc)" = 1000
usermod --password "*" hpc
mkdir -p /home/hpc/.ssh /home/hpc/.kube /etc/hpc /run/sshd
chmod 700 /home/hpc/.ssh /home/hpc/.kube
mkdir -p /srv/hpc/input /srv/hpc/output /srv/hpc/logs
chown 1000:1000 /srv/hpc /srv/hpc/input /srv/hpc/output /srv/hpc/logs
cp /etc/kubernetes/admin.conf /home/hpc/.kube/config
chmod 600 /home/hpc/.kube/config
ssh-keygen -A
cat > /etc/ssh/sshd_config.d/hpc.conf <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers hpc
EOF
'
docker cp "$SSH_PUBLIC_KEY" "$HEAD:/home/hpc/.ssh/authorized_keys"
docker cp "$ROOT/scripts/hpc.py" "$HEAD:/usr/local/lib/hpc.py"
python3 "$ROOT/scripts/hpc.py" config > "$ROOT/.runtime/client.json"
docker cp "$ROOT/.runtime/client.json" "$HEAD:/etc/hpc/client.json"
# kubectl disertakan image node kind; validasi sebelum mengaktifkan login.
docker exec "$HEAD" bash -ceu '
command -v kubectl
cat > /usr/local/bin/hpc <<"EOF"
#!/bin/bash
exec python3 /usr/local/lib/hpc.py "$@"
EOF
chmod 755 /usr/local/bin/hpc
chmod 600 /home/hpc/.ssh/authorized_keys
chown -R hpc:hpc /home/hpc/.ssh /home/hpc/.kube
sshd -t
systemctl enable --now ssh
'
