import requests, subprocess, threading, time

peak = []
def watch():
    while True:
        o = subprocess.run(["docker","stats","--no-stream","--format","{{.MemUsage}}","parser"],
                           capture_output=True, text=True).stdout.strip()
        if o: peak.append(o)
        time.sleep(1)
threading.Thread(target=watch, daemon=True).start()

codes = [requests.post("http://localhost:8000/parse",
         json={"text": "set an alarm for seven am"}).status_code for _ in range(50)]
time.sleep(2)

oom = subprocess.run(["docker","inspect","parser","--format","{{.State.OOMKilled}}"],
                     capture_output=True, text=True).stdout.strip()
out = f"{codes.count(200)} of 50 OK\nOOMKilled={oom}\nmemory samples: {peak}\n"
print(out)
open("results/task3_limits.txt","w").write(out)