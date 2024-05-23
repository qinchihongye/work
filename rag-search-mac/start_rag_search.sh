# 找到所有匹配的进程ID并逐一杀死
for pid in $(lsof -i:8069 -t); do
    echo "Killing process $pid"
    kill -9 "$pid"
done


nohup bash -c "source /home/ubuntu/anaconda3/bin/activate rag-search && python3 rag_main.py" > logs/output.log 2>&1 &

sleep 5s

pids=$(ps -ef | grep 'rag_main' | grep -v grep | awk '{printf("%s ", $2)}')

for pid in ${pids}; do
    echo "进程启动成功 $pid"
done