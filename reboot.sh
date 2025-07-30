sudo systemctl daemon-reload
sudo systemctl enable fastapi.service worker.service
sudo systemctl start fastapi.service worker.service

sudo systemctl restart fastapi.service worker.service


sudo systemctl stop fastapi.service worker.service

# send SIGKILL to every process in the service control group
sudo systemctl kill --kill-who=all --signal=KILL fastapi.service

# logs
sudo systemctl status fastapi.service
systemctl list-units --type=service --state=running 'worker@*'
sudo journalctl -u worker.service -f
