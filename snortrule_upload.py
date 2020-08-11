import os
import sys


container_list = []

container_list = os.popen("docker container ls | awk '{print $1}' | tail -n+2").readlines()

file_name = sys.argv[1]


for x in range(len(container_list)):
    print container_list[x]
    command = str("docker cp ") + str(file_name) + " " + str.rstrip(container_list[x]) + str(":/etc/snort/rules")
    os.popen(command).read()
