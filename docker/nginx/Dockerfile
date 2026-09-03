FROM nginx:1.27-alpine

# 移除預設設定
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf

# SSL 證書由 volume mount 提供（docker-compose.prod.yml）
# 預設建立目錄避免 mount 失敗
RUN mkdir -p /etc/nginx/ssl

EXPOSE 80 443
