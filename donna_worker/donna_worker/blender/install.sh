sudo apt install -y wget ca-certificates libsm6 libxrender1 libxext6 libx11-6 libxt6 libfontconfig1 libcups2 libxi6 libxrandr2 libxinerama1
wget https://ftp.halifax.rwth-aachen.de/blender/release/Blender4.4/blender-4.4.3-linux-x64.tar.xz -O /tmp/blender.tar.xz
sudo tar -C /opt -xJf /tmp/blender.tar.xz
sudo ln -s /opt/blender-4.4.3-linux-x64/blender /usr/local/bin/blender
rm /tmp/blender.tar.xz

blender -v