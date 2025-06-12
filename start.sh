#!/bin/bash

# 定义程序名称
PROGRAM_NAME="feishu_plus_app.py"
# 定义虚拟环境名称
VENV_NAME="feishu-plus"

# (root)激活虚拟环境
#source activate $VENV_NAME

# (llmuser)初始化 conda
source /export/llmuser/anaconda3/etc/profile.d/conda.sh
conda activate $VENV_NAME

# 查找正在运行的程序
PID=$(pgrep -f $PROGRAM_NAME)

if [ -n "$PID" ]; then
    echo "Stopping existing instance of $PROGRAM_NAME with PID $PID..."
    kill $PID
    sleep 2  # 等待进程完全停止
else
    echo "No existing instance of $PROGRAM_NAME found."
fi

# 启动新的实例
echo "Starting $PROGRAM_NAME..."
nohup python $PROGRAM_NAME &

echo "$PROGRAM_NAME has been started."


