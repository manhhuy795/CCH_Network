import subprocess

res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
for line in res.stdout.splitlines():
    if "python" in line or "osken" in line or "topo" in line or "mininet" in line:
        print(line)
