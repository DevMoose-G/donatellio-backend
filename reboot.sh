sudo systemctl daemon-reload
sudo systemctl enable fastapi.service worker.service
sudo systemctl start fastapi.service worker.service

sudo systemctl restart fastapi.service worker.service


sudo systemctl stop fastapi.service worker.service

# logs
sudo systemctl status fastapi.service
sudo journalctl -u fastapi.service -f
