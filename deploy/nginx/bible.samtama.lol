# nginx site: bible.samtama.lol → 127.0.0.1:5555 (docker bible-bot)
#
# Install (Debian/Ubuntu style):
#   sudo cp deploy/nginx/bible.samtama.lol /etc/nginx/sites-available/bible.samtama.lol
#   sudo ln -sf /etc/nginx/sites-available/bible.samtama.lol /etc/nginx/sites-enabled/bible.samtama.lol
#   sudo nginx -t && sudo systemctl reload nginx
#   sudo certbot --nginx -d bible.samtama.lol
#
# Do NOT open ufw for 5555. Only nginx on the host talks to the container.

server {
    listen 80;
    listen [::]:80;
    server_name bible.samtama.lol;

    # Optional: if you installed logging/ops vps-security snippets
    # include /etc/nginx/snippets/block-probes.conf;

    # Webhook + health (Telegram posts to /webhook)
    location / {
        proxy_pass http://127.0.0.1:5555;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Multi-chapter Bible fetches can take several seconds
        proxy_connect_timeout 10s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    access_log /var/log/nginx/bible.samtama.lol.access.log;
    error_log  /var/log/nginx/bible.samtama.lol.error.log;
}
