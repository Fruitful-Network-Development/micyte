# Copyright 2025 Dylan Montgomery
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# mycite_project/main.py
# AUTHOR:   Dylan Montgomery
# MODIFIED:	2025-10-20
# VERSION:	10.04.04
# PURPOSE:  HERE
# NOTES:    -COLOR_1 = "#dedbec"  # icy lilac ; COLOR_2 = "#3f403a"  # dark green ; COLOR_3 = "#b9b8ac"  # beige ; COLOR_4 = "#2f302b"  # charcoal

import threading
import time
from MSS_convention import MSS
from directive_engine import DirectiveEngine
from sockets.portal_ui import Portal

class AppState:
    def __init__(self):      
        self.running = True
        self.poll_ms = 100
        
        self.hid_flag, self.net_flag, self.pri_flag = False
        self.hid_buffer, self.net_buffer, self.pri_buffer: list[bytes] = []
        
        self.mss_systm = MSS()
        
        self.mss_systm.boot()
        self.mss_systm.boot_load()
        self.objects = getattr(self.mss_systm, 'flmnt_ssid', None)
        self.obj_tree = getattr(self.mss_systm, 'ssid_g', None)
        
        self.hanus_current = 0
        
        self.time_flag = False;
        self.time_sandbox = [];
        self.time_cursor = [];
        
        self.tkinter_socket = Portal(self)
        self.hanus = DirectiveEngine(self)

    def enqueue_hid(self, datum: bytes) -> None:
        was_empty = not self.hid_buffer
        self.hid_buffer.append(datum)
        self.hid_flag = True

    def enqueue_net(self, datum: bytes) -> None:
        was_empty = not self.net_buffer
        self.net_buffer.append(datum)
        self.net_flag = True

    def enqueue_pri(self, datum: bytes) -> None:
        was_empty = not self.pri_buffer
        self.pri_buffer.append(datum)
        self.pri_flag = True
    
    def main_loop(self, sleep_s: float = 0.01):
        while self.running:
            # HID isolation
            if self.hid_flag:
                while self.hid_flag and self.running:
                    self.hanus.directive(self.hid_buffer.pop(0), self.hanus_attention)
                    if len(self.hid_buffer) == 0:
                        self.hid_flag = False
                time.sleep(sleep_s)
                continue  # restart outer loop after HID isolation
            # One-shot checks for NET/PRI
            if self.net_flag:
                self.hanus.daemon((self.net_buffer.pop(0)), ())
                if len(self.net_buffer) == 0:
                    self.net_flag = False
            if self.pri_flag:
                self.hanus.daemon(((self.pri_buffer.pop(0)), ())
                if len(self.net_buffer) == 0:
                    self.net_flag = False
            time.sleep(sleep_s)

def main():
    app = AppState();
    
    # Run the scheduler loop on a worker thread
    t = threading.Thread(target=app.main_loop, daemon=True)
    t.start()
    
    app.tkinter_socket.start()

if __name__ == '__main__':
    main()
