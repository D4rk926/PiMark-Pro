import sys
import os
import psutil
import subprocess
import socket
import time

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

import pyqtgraph as pg
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFrame, QStackedWidget, QProgressBar)
from PyQt5.QtCore import QTimer, Qt

# --- GLOBÁLIS DESIGN ---
app.setStyleSheet("""
    QMainWindow, QWidget { background-color: #000000; color: #ffffff; border: none; }
    QLabel { background: transparent; border: none; }
    QProgressBar { border: 1px solid #333; background-color: #111; height: 10px; }
    QProgressBar::chunk { background-color: #ff0000; }
""")

class MainMenu(QWidget):
    def __init__(self, start_lab_callback, get_data_func):
        super().__init__()
        self.get_data = get_data_func
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("PiMark Pro")
        title.setStyleSheet("font-size: 80px; font-weight: bold; color: #ff0000;")
        layout.addWidget(title)

        self.m_stats = QLabel("Scanning...")
        self.m_stats.setStyleSheet("font-size: 20px; color: #888;")
        layout.addWidget(self.m_stats)

        layout.addSpacing(50)

        btn = QPushButton("ENTER TEST LAB")
        btn.setFixedSize(400, 100)
        btn.setStyleSheet("background-color: #ff0000; color: white; border-radius: 10px; font-size: 26px; font-weight: bold;")
        btn.clicked.connect(start_lab_callback)
        layout.addWidget(btn)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_menu)
        self.timer.start(1000)

    def update_menu(self):
        d = self.get_data()
        self.m_stats.setText(f"TEMP: {d['temp']}°C | IP: {d['ip']}")

class ResultScreen(QWidget):
    def __init__(self, back_callback):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("BENCHMARK RESULTS")
        title.setStyleSheet("font-size: 45px; font-weight: bold; color: #ff0000; margin-bottom: 20px;")
        layout.addWidget(title)

        self.res_label = QLabel("")
        self.res_label.setStyleSheet("font-size: 22px; color: #fff; padding: 30px; background: #0a0a0a; border: 2px solid #ff0000; border-radius: 10px;")
        layout.addWidget(self.res_label)

        back_btn = QPushButton("RETURN TO LAB")
        back_btn.setFixedSize(300, 70)
        back_btn.setStyleSheet("background-color: #ff0000; color: white; font-weight: bold; font-size: 18px; margin-top: 30px;")
        back_btn.clicked.connect(back_callback)
        layout.addWidget(back_btn)

    def show_results(self, s):
        rating = "EXCELLENT" if s['max_temp'] < 65 else "GOOD" if s['max_temp'] < 78 else "THERMAL LIMIT REACHED"
        text = (f"MAX TEMPERATURE:  {s['max_temp']} °C\n"
                f"MAX CLOCK SPEED: {s['max_clock']} MHz\n"
                f"MAX RAM USED:    {s['max_ram']} MB\n"
                f"MAX VOLTAGE:     {s['max_volt']} V\n"
                f"THROTTLING:      {s['throttled']}\n\n"
                f"COOLING PERFORMANCE: {rating}")
        self.res_label.setText(text)

class TestLab(QWidget):
    def __init__(self, back_callback, show_results_callback, get_data_func):
        super().__init__()
        self.get_data = get_data_func
        self.back_callback = back_callback
        self.show_results_callback = show_results_callback
        
        self.stress_proc = None
        self.is_timed = False
        self.test_start_time = 0
        self.test_duration = 300 # 5 perc
        
        self.bench_stats = {'temps': [], 'clocks': [], 'rams': [], 'volts': [], 'throttled': "No"}
        self.data = {'temp': [], 'cpu': [], 'clock': [], 'volt': []}
        self.time_axis = []
        self.elapsed = 0

        self.setup_ui()
        
        self.g_timer = QTimer()
        self.g_timer.timeout.connect(self.update_graphs)
        self.g_timer.start(100)

        self.t_timer = QTimer()
        self.t_timer.timeout.connect(self.update_ui_slow)
        self.t_timer.start(1000)

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        
        # --- OLDALPANEL ---
        side = QFrame()
        side.setFixedWidth(380)
        side.setStyleSheet("background-color: #080808; border-right: 2px solid #ff0000;")
        side_layout = QVBoxLayout(side)

        back_btn = QPushButton("← EXIT TO MENU")
        back_btn.setStyleSheet("background-color: #ff0000; color: white; font-weight: bold; padding: 15px;")
        back_btn.clicked.connect(self.stop_and_back)
        side_layout.addWidget(back_btn)

        side_layout.addSpacing(10)

        # INFÓK (Visszaállítva minden)
        self.labels = {}
        info_cfg = [("temp", "TEMP", "#ff3300"), ("cpu", "CPU LOAD", "#0099ff"), 
                    ("clock", "CLOCK", "#ffae00"), ("ram", "RAM (MB)", "#00ff99"),
                    ("volt", "VOLTAGE", "#cc00ff"), ("fan", "FAN SPEED", "#ffffff"),
                    ("disk", "STORAGE", "#aaaaaa"), ("status", "STATUS", "#ffff00"),
                    ("ip", "LOCAL IP", "#00ffff"), ("uptime", "UPTIME", "#ff00ff")]

        for key, name, col in info_cfg:
            lbl = QLabel(f"{name}: --")
            lbl.setStyleSheet(f"font-size: 13px; color: {col}; padding: 6px; background: #111; border-left: 3px solid {col}; margin-bottom: 2px;")
            side_layout.addWidget(lbl)
            self.labels[key] = lbl

        side_layout.addSpacing(15)
        
        # PROCESS MONITOR (Működő verzió)
        p_title = QLabel("LIVE PROCESS MONITOR")
        p_title.setStyleSheet("font-weight: bold; color: #ff0000; font-size: 15px; margin-top: 10px;")
        side_layout.addWidget(p_title)

        self.proc_widgets = []
        for _ in range(5):
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 2, 0, 2)
            n = QLabel("---")
            n.setStyleSheet("color: white; font-size: 11px;")
            b = QProgressBar()
            l.addWidget(n, 2); l.addWidget(b, 3)
            self.proc_widgets.append((n, b))
            side_layout.addWidget(w)

        side_layout.addStretch()

        # TEST GOMBOK
        self.btn_normal = QPushButton("START STRESS TEST")
        self.btn_normal.setStyleSheet("background-color: #ff0000; padding: 20px; font-weight: bold; font-size: 16px; margin-bottom: 5px;")
        self.btn_normal.clicked.connect(lambda: self.toggle_test(timed=False))
        side_layout.addWidget(self.btn_normal)

        self.btn_timed = QPushButton("START 5-MIN BENCHMARK")
        self.btn_timed.setStyleSheet("background-color: #800000; padding: 20px; font-weight: bold; font-size: 16px;")
        self.btn_timed.clicked.connect(lambda: self.toggle_test(timed=True))
        side_layout.addWidget(self.btn_timed)

        main_layout.addWidget(side)

        # GRAFIKONOK
        graph_layout = QVBoxLayout()
        self.curves = {}
        for k, t, c in [('temp', 'TEMP (°C)', '#ff3300'), ('cpu', 'CPU (%)', '#0099ff'), 
                        ('clock', 'CLOCK (MHz)', '#ffae00'), ('volt', 'VOLT (V)', '#cc00ff')]:
            pw = pg.PlotWidget(title=t)
            pw.setBackground('#000000')
            self.curves[k] = pw.plot(pen=pg.mkPen(color=c, width=2))
            graph_layout.addWidget(pw)
        main_layout.addLayout(graph_layout)

    def toggle_test(self, timed=False):
        if self.stress_proc:
            self.stop_test(manual=True)
        else:
            self.start_test(timed)

    def start_test(self, timed):
        self.is_timed = timed
        self.test_start_time = time.time()
        self.bench_stats = {'temps': [], 'clocks': [], 'rams': [], 'volts': [], 'throttled': "No"}
        
        self.stress_proc = subprocess.Popen(["stress-ng", "--cpu", "0", "--matrix-size", "128"])
        self.btn_normal.setEnabled(not timed)
        self.btn_timed.setText("STOP TEST")
        self.btn_timed.setStyleSheet("background-color: #444; padding: 20px; font-weight: bold;")

    def stop_test(self, manual=True):
        if not self.stress_proc: return
        self.stress_proc.terminate()
        self.stress_proc = None
        
        self.btn_normal.setEnabled(True)
        self.btn_timed.setText("START 5-MIN BENCHMARK")
        self.btn_timed.setStyleSheet("background-color: #800000; padding: 20px;")

        if self.is_timed and not manual:
            s = self.bench_stats
            final = {
                'max_temp': max(s['temps']) if s['temps'] else 0,
                'max_clock': max(s['clocks']) if s['clocks'] else 0,
                'max_ram': max(s['rams']) if s['rams'] else 0,
                'max_volt': max(s['volts']) if s['volts'] else 0,
                'throttled': s['throttled']
            }
            self.show_results_callback(final)

    def update_graphs(self):
        s = self.get_data()
        self.elapsed += 0.1
        self.time_axis.append(self.elapsed)
        for k in ['temp', 'cpu', 'clock', 'volt']:
            self.data[k].append(s[k])
            if len(self.time_axis) > 150: self.data[k].pop(0)
            self.curves[k].setData(self.time_axis[-len(self.data[k]):], self.data[k])
        
        # BIZTONSÁGI STOP (85C)
        if s['temp'] > 85:
            self.stop_test(manual=False)

    def update_ui_slow(self):
        s = self.get_data()
        self.labels['temp'].setText(f"TEMP: {s['temp']} °C")
        self.labels['cpu'].setText(f"CPU LOAD: {s['cpu']} %")
        self.labels['clock'].setText(f"CLOCK: {s['clock']} MHz")
        self.labels['ram'].setText(f"RAM: {s['ram'][0]} / {s['ram'][1]} MB")
        self.labels['volt'].setText(f"VOLTAGE: {s['volt']} V")
        self.labels['fan'].setText(f"FAN SPEED: {s['fan']} %")
        self.labels['disk'].setText(f"STORAGE: {s['disk']} %")
        self.labels['status'].setText(f"STATUS: {s['throttle']}")
        self.labels['ip'].setText(f"LOCAL IP: {s['ip']}")
        self.labels['uptime'].setText(f"UPTIME: {int(time.time() - self.test_start_time) if self.stress_proc else 0}s")

        if self.stress_proc:
            self.bench_stats['temps'].append(s['temp'])
            self.bench_stats['clocks'].append(s['clock'])
            self.bench_stats['rams'].append(s['ram'][0])
            self.bench_stats['volts'].append(s['volt'])
            if s['throttle'] != "OK": self.bench_stats['throttled'] = "Yes"
            if self.is_timed and (time.time() - self.test_start_time >= self.test_duration):
                self.stop_test(manual=False)

        # PROCESSES
        try:
            procs = sorted(psutil.process_iter(['name', 'cpu_percent']), key=lambda x: x.info['cpu_percent'], reverse=True)[:5]
            for i, p in enumerate(procs):
                if i < 5:
                    self.proc_widgets[i][0].setText(p.info['name'][:12])
                    self.proc_widgets[i][1].setValue(int(p.info['cpu_percent']))
        except: pass

    def stop_and_back(self):
        self.stop_test()
        self.back_callback()

class PiMarkWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiMark Pro")
        self.resize(1500, 950)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.menu = MainMenu(lambda: self.stack.setCurrentIndex(1), self.fetch)
        self.lab = TestLab(lambda: self.stack.setCurrentIndex(0), self.show_res, self.fetch)
        self.res = ResultScreen(lambda: self.stack.setCurrentIndex(1))
        self.stack.addWidget(self.menu); self.stack.addWidget(self.lab); self.stack.addWidget(self.res)

    def show_res(self, s):
        self.res.show_results(s)
        self.stack.setCurrentIndex(2)

    def fetch(self):
        def cmd(c): return os.popen(f"vcgencmd {c}").readline()
        try:
            t = float(cmd("measure_temp").replace("temp=","").replace("'C\n","") or 0)
            c = int(cmd("measure_clock arm").split("=")[1]) // 1000000
            v = float(cmd("measure_volts core").split("=")[1].replace("V\n","") or 0)
            th = "OK" if "0x0" in cmd("get_throttled") else "THROTTLE!"
            f = 0
            if os.path.exists("/sys/class/thermal/cooling_device0/cur_state"):
                with open("/sys/class/thermal/cooling_device0/cur_state", "r") as fl: f = int(fl.read().strip()) * 25
            ip = socket.gethostbyname(socket.gethostname())
        except: t, c, v, th, f, ip = 0, 0, 0, "N/A", 0, "127.0.0.1"
        m = psutil.virtual_memory(); d = psutil.disk_usage('/')
        return {'temp': t, 'cpu': psutil.cpu_percent(), 'clock': c, 'ram': (m.used//1048576, m.total//1048576), 'volt': v, 'throttle': th, 'fan': f, 'disk': d.percent, 'ip': ip}

if __name__ == "__main__":
    w = PiMarkWindow()
    w.show()
    sys.exit(app.exec_())
