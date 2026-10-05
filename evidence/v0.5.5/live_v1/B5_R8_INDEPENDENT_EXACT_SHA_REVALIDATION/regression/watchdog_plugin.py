import faulthandler, os, sys, threading, time
from pathlib import Path
state = {"last": time.monotonic(), "node": "<collection/start>"}
out = os.environ["B5R8_STALL_FILE"]
def report():
    while True:
        time.sleep(1)
        if time.monotonic() - state["last"] >= 90:
            with open(out, "a", buffering=1) as f:
                f.write(f"STALL pid={os.getpid()} elapsed_no_progress={time.monotonic()-state['last']:.1f}s node={state['node']}\nTHREAD_STACKS_BEGIN\n")
                faulthandler.dump_traceback(file=f, all_threads=True)
                f.write("THREAD_STACKS_END\n")
            return
class Watch:
    def pytest_runtest_logstart(self, nodeid, location):
        state["last"] = time.monotonic(); state["node"] = nodeid
    def pytest_runtest_logreport(self, report):
        state["last"] = time.monotonic(); state["node"] = report.nodeid
    def pytest_sessionfinish(self, session, exitstatus):
        state["last"] = time.monotonic()
def pytest_configure(config):
    config.pluginmanager.register(Watch(), "b5r8-readonly-watch")
    threading.Thread(target=report, daemon=True, name="b5r8-stall-watch").start()
