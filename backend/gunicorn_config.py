import os
import multiprocessing

workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
ws = "wsproto"
