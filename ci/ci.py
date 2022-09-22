with open('./ci/cilog.txt', 'r') as log:
    lines = log.readlines()
    line_num = len(lines) - 2
    line = lines[line_num]
    if "10.00" in line:
        exit(0)
    else:
        exit(1)
