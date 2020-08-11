import os
import sys


container_list = []

container_list = os.popen("docker container ls | awk '{print $1}' | tail -n+2").readlines()

file_name = sys.argv[1]


for x in range(len(container_list)):
    print container_list[x],
    command = "docker cp " + file_name + " " + container_list[x] + ":/etc/snort/rules"
    print(command)
