with open("core/live_pipeline.py", "r") as f:
    lines = f.readlines()

out = []
state = 0
for line in lines:
    if line.startswith("def run_live_pipeline"):
        out.append(line)
        state = 1
    elif state == 1 and line.startswith("    except"):
        out.append(line)
        state = 2
    elif state == 2 and line.startswith("    finally:"):
        out.append(line)
        state = 3
    elif state == 0:
        out.append(line)
    elif state == 1:
        if line.strip(): out.append("    " + line)
        else: out.append(line)
    elif state == 2:
        out.append(line)
    elif state == 3:
        if line.strip(): out.append("        " + line)
        else: out.append(line)

with open("core/live_pipeline.py", "w") as f:
    for line in out:
        f.write(line)
