#!/usr/bin/env bash
set -eo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo 'Run through wsl.exe -d WHEELTEC-Ubuntu-22.04 -u root.' >&2
  exit 1
fi
. /etc/os-release
[[ "$VERSION_ID" == '22.04' && "$ID" == 'ubuntu' ]] || exit 1
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
apt_options=(-o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 -o Acquire::http::Timeout=45 -o Acquire::https::Timeout=45)

if ! id wheeltec >/dev/null 2>&1; then
  adduser --disabled-password --gecos '' wheeltec
fi
usermod -aG sudo wheeltec
python3 - <<'PY'
import configparser
from pathlib import Path
p = Path('/etc/wsl.conf')
c = configparser.ConfigParser()
c.read(p)
if not c.has_section('user'):
    c.add_section('user')
c['user']['default'] = 'wheeltec'
with p.open('w') as f:
    c.write(f)
PY

echo '=== Updating the new Ubuntu system ==='
apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
apt-get "${apt_options[@]}" upgrade -y
apt-get "${apt_options[@]}" install -y --no-install-recommends ca-certificates curl locales
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8

echo '=== Configuring the official ROS repository ==='
ros_source_version=1.3.0
install -d /var/cache/wheeltec-setup
ros_source_deb="/var/cache/wheeltec-setup/ros2-apt-source_${ros_source_version}.jammy_all.deb"
curl --fail --location --silent --show-error --retry 3 --connect-timeout 20 --max-time 300 \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ros_source_version}/ros2-apt-source_${ros_source_version}.jammy_all.deb" \
  --output "$ros_source_deb"
dpkg-deb -f "$ros_source_deb" Package Version
[[ $(dpkg-deb -f "$ros_source_deb" Package) == ros2-apt-source ]]
[[ $(dpkg-deb -f "$ros_source_deb" Version) == "${ros_source_version}~jammy" ]]
dpkg -i "$ros_source_deb"
apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update

echo '=== Installing ROS, Fortress, SLAM and navigation tools ==='
apt-get "${apt_options[@]}" install -y --no-install-recommends \
  ros-humble-desktop ros-humble-ros-gz \
  ros-humble-navigation2 ros-humble-nav2-bringup ros-humble-slam-toolbox \
  ros-dev-tools mesa-utils x11-utils dbus-x11

echo '=== Preparing the development user ==='
if ! grep -Fq 'source /opt/ros/humble/setup.bash' /home/wheeltec/.bashrc; then
  printf '\nsource /opt/ros/humble/setup.bash\nexport ROS_LOCALHOST_ONLY=1\nexport ROS_DOMAIN_ID=77\n' >> /home/wheeltec/.bashrc
fi
install -d -o wheeltec -g wheeltec /home/wheeltec/wheeltec_sim_ws/src /home/wheeltec/simulation-checks
chown wheeltec:wheeltec /home/wheeltec/.bashrc
echo '=== Provisioning finished; runtime verification still required ==='
