import time
from progress.bar import IncrementalBar

bar = IncrementalBar('Processing', max=100)
for i in range(100):
    time.sleep(0.1)
    bar.next()
bar.finish()