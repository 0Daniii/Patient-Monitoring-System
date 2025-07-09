# Broadcaster.py V6
import queue
import threading

class EventBroadcaster:
    def __init__(self):
        self.listeners = []
        self.lock = threading.Lock()

    def listen(self):
        q = queue.Queue(maxsize=10)
        with self.lock:
            self.listeners.append(q)
        return q

    def broadcast(self, msg: str):
        with self.lock:
            for q in list(self.listeners):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    self.listeners.remove(q)

# single shared instance
broadcaster = EventBroadcaster()
