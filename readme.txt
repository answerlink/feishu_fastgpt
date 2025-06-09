# 前端使用nginx启动
docker run -d --restart=always --name feishu-frontend -p 18055:80 -v /home/service/feishu_fastgpt/web/dist:/usr/share/nginx/html/dist -v /home/service/feishu_fastgpt/nginx_app.conf:/etc/nginx/conf.d/default.conf nginx:latest

# 前端停止
docker rm -f feishu-frontend

# 后台nohup启动 脚本启动
sh start.sh

