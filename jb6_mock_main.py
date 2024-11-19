import cv2
import serial
import sys
import time
from roboflowoak import RoboflowOak
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QFrame, QTextEdit, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

class MockArduino:
    def __init__(self):
        print("Initialized Mock Arduino for testing")
        self.is_mock = True
        
    def write(self, command):
        print(f"Mock Arduino received command: {command.decode().strip()}")
        return True
        
    def readline(self):
        return b"ok\n"
        
    def close(self):
        print("Mock Arduino connection closed")

def initialize_arduino(port="/dev/ttyACM0", baud_rate=9600):
    try:
        arduino = serial.Serial(port, baud_rate)
        print(f"Connected to real Arduino on {port}")
        arduino.is_mock = False
        return arduino
    except serial.SerialException as e:
        print(f"Arduino not found on {port}: {e}")
        print("Initializing Mock Arduino for testing")
        return MockArduino()

port = "/dev/ttyACM0"
baud_rate = 9600
command_delay = 1
arduino = initialize_arduino(port, baud_rate)

machine_dimensions = [(0, 3.45), (0, 3.6), (0, 0.325)]
mmpp = [0.41, -0.41]
offsets = [150, 262]

def send_gcode(command):
    command = str.encode(command.strip() + '\n')
    arduino.write(command)
    response = arduino.readline()
    if not getattr(arduino, 'is_mock', False):
        time.sleep(command_delay)
    return response.strip()

def pickup_sequence(x, y):
    return [
        f"G01 x{((mmpp[0]*x)+offsets[0])/100} y{((mmpp[1]*y)+offsets[1])/100} f300",
        "M08",
        f"G01 z{machine_dimensions[2][1]} f300",
        "G01 z0 f300",
        "G01 x0 y0 f300",
        "M09"
    ]

class OAK_GUI(QMainWindow):
    def __init__(self, video_scale=0.6):
        super().__init__()

        print("Initializing RoboflowOak...")
        self.roboflowoak_active = True
        try:
            self.roboflowoak = RoboflowOak(model="jellybelly5", confidence=0.10, overlap=0.5,
                                version="1", api_key="##INSERT YOUR API KEY HERE###", rgb=True,
                                depth=False, device=None, blocking=True)
        except:
            print("RoboflowOak initialization failed!")
            self.roboflowoak_active = False
        
        self.video_running = False
        self.snapshot_mode = False
        self.flavor_coordinates = {}
        self.video_scale = video_scale
        self.last_message = ""
        self.snapshot_frame = None
        
        print("Initializing UI...")
        self.initUI()
        
        # Display Arduino and RoboflowOak status
        self.display_message("RoboflowOak is " + ("active!" if self.roboflowoak_active else "inactive!"))
        self.display_message("Using " + ("Mock Arduino (Testing Mode)" if getattr(arduino, 'is_mock', False) else f"Real Arduino on {port}"))

    def initUI(self):
        self.setWindowTitle("Jelly Bean Sorter" + (" (Testing Mode)" if getattr(arduino, 'is_mock', False) else ""))
        self.setMinimumSize(1024, 700)
        self.setMaximumHeight(720)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        top_layout = QHBoxLayout()
        table_layout = QVBoxLayout()

        button_layout = QVBoxLayout()
        button_layout.setSpacing(3)
        table_layout.QVBoxLayout()

        # Video frame with reduced size
        self.video_frame = QLabel()
        self.video_frame.setFixedSize(int(640*self.video_scale), int(640*self.video_scale))
        self.video_frame.setFrameStyle(QFrame.Sunken | QFrame.Panel)
        top_layout.addWidget(self.video_frame)

        # Create buttons with smaller size
        button_size = (100, 35)

        # Main control buttons
        self.start_button = QPushButton("Start Video", self)
        self.start_button.setFixedSize(*button_size)
        self.start_button.clicked.connect(self.start_video)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Video", self)
        self.stop_button.setFixedSize(*button_size)
        self.stop_button.clicked.connect(self.stop_video)
        button_layout.addWidget(self.stop_button)

        self.snapshot_button = QPushButton("Snapshot", self)
        self.snapshot_button.setFixedSize(*button_size)
        self.snapshot_button.clicked.connect(self.snapshot)
        button_layout.addWidget(self.snapshot_button)

        self.action_button = QPushButton("Pick Flavor", self)
        self.action_button.setFixedSize(*button_size)
        self.action_button.clicked.connect(self.pick_flavor)
        button_layout.addWidget(self.action_button)

        self.auto_button = QPushButton("Auto Pick", self)
        self.auto_button.setFixedSize(*button_size)
        self.auto_button.clicked.connect(self.auto_pick)
        button_layout.addWidget(self.auto_button)

        # Add Config section label
        config_label = QLabel("Config")
        config_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        button_layout.addWidget(config_label)

        # Add configuration buttons
        self.home_button = QPushButton("Home", self)
        self.home_button.setFixedSize(*button_size)
        self.home_button.clicked.connect(self.home_machine)
        button_layout.addWidget(self.home_button)

        self.zero_button = QPushButton("Zero", self)
        self.zero_button.setFixedSize(*button_size)
        self.zero_button.clicked.connect(self.zero_machine)
        button_layout.addWidget(self.zero_button)

        self.reset_button = QPushButton("Reset", self)
        self.reset_button.setFixedSize(*button_size)
        self.reset_button.clicked.connect(self.reset_machine)
        button_layout.addWidget(self.reset_button)

        # Add Arduino status indicator
        self.arduino_status = QLabel("Arduino: " + ("Mock (Testing)" if getattr(arduino, 'is_mock', False) else "Connected"))
        self.arduino_status.setStyleSheet("color: " + ("orange" if getattr(arduino, 'is_mock', False) else "green"))
        button_layout.addWidget(self.arduino_status)

        # Configure predictions table
        self.predictions_table = QTableWidget()
        self.predictions_table.setColumnCount(3)
        self.predictions_table.setHorizontalHeaderLabels(['Flavor', 'Avg Confidence', 'Coordinates'])
        
        # Set minimum width for the table and its columns
        self.predictions_table.setMinimumWidth(400)
        header = self.predictions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setMinimumSectionSize(120)
        
        table_layout.addWidget(self.predictions_table)

        # Configure message box
        self.message_box = QTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setMaximumHeight(100)
        self.message_box.setMaximumHeight(100)

        # Combine layouts
        top_layout.addLayout(button_layout)
        top_layout.addLayout(table_layout)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.message_box)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.start_video()
    
    def display_message(self, message):
        print(message)
        self.message_box.append(message)
        self.last_message = message
    
    def start_video(self):
        self.video_running = True
        self.snapshot_mode = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(1)

    def stop_video(self):
        self.video_running = False
        self.timer.stop()
        # Don't clear the frame if we're in snapshot mode
        if not self.snapshot_mode:
            self.video_frame.clear()
            self.predictions_table.setRowCount(0)
    
    def snapshot(self):
        if self.video_running:
            self.snapshot_mode = True
            self.video_running = False
            self.timer.stop()
            # Store current frame
            self.snapshot_frame = self.video_frame.pixmap()
            self.display_message("Snapshot taken")

    def pick_flavor(self):
        selected_items = self.predictions_table.selectedItems()
        if not selected_items:
            self.display_message("No flavor selected!")
            return
            
        selected_flavor = selected_items[0].text()
        if selected_flavor:
            coords = self.flavor_coordinates.get(selected_flavor)
            if coords:
                x = abs(int(640-coords[0]))
                y = abs(int(640-coords[1]))

                gcode_commands = pickup_sequence(x,y)

                send_gcode("Wakeup... or else...")
                time.sleep(2)

                self.display_message("Picking up: " + selected_flavor)
                for command in gcode_commands:
                    self.display_message("Sending:\t" + command)
                    send_gcode(command)
            else:
                self.display_message("That flavor's coordinates don't exist!")
        else:
            self.display_message("No flavor selected!")

    def auto_pick(self):
        while self.predictions_table.item(0,0):
            self.snapshot()
            bean = self.predictions_table.item(0,0).text()
            coords = self.predictions_table.item(0,2).text().split(",")
            gcode_commands = pickup_sequence(int(coords[0]), int(coords[1]))

            self.display_message("Picking up: " + bean)
            for command in gcode_commands:
                self.display_message("Sending:\t" + command)
                send_gcode(command)

            self.start_video()
            self.update_frame()

        send_gcode("G01 x0 y0 f300")
        return True

    def home_machine(self):
        self.display_message("Homing machine...")
        send_gcode("$h")
        
    def zero_machine(self):
        self.display_message("Setting machine zero point...")
        send_gcode("G28")
        
    def reset_machine(self):
        self.display_message("Resetting machine...")
        send_gcode("$x")
  
    def update_frame(self):
        if not self.video_running:
            if self.snapshot_mode and self.snapshot_frame is not None:
                self.video_frame.setPixmap(self.snapshot_frame)
            return
        
        try:
            result, frame, raw_frame, __ = self.roboflowoak.detect()
            image = raw_frame
            predictions = result.get("predictions", [])

            flavors_data = {}
            self.flavor_coordinates.clear()

            for prediction in predictions:
                label = prediction.class_name
                confidence = prediction.confidence
                x, y = prediction.x, prediction.y

                self.flavor_coordinates[label] = (x, y)

                if label in flavors_data:
                    flavors_data[label]['count'] += 1
                    flavors_data[label]['total_confidence'] += confidence
                else:
                    flavors_data[label] = {'count': 1, 'total_confidence': confidence}
            
            flavor_stats = [(flavor, data['count'], data['total_confidence'] / data['count']) 
                           for flavor, data in flavors_data.items()]
            flavor_stats.sort(key=lambda x: (-x[2], -x[1]))

            self.predictions_table.setRowCount(len(flavor_stats))

            for i, (flavor, count, avg_conf) in enumerate(flavor_stats):
                coords = self.flavor_coordinates.get(flavor, ('N/A', 'N/A'))
                text_size = cv2.getTextSize(flavor, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
                x = abs(int(640-coords[0]))
                y = abs(int(640-coords[1]))

                self.predictions_table.setItem(i, 0, QTableWidgetItem(flavor))
                self.predictions_table.setItem(i, 1, QTableWidgetItem(f"{avg_conf:.2f}"))
                self.predictions_table.setItem(i, 2, QTableWidgetItem(f"{x}, {y}"))

                image = cv2.flip(image, 0)
                image = cv2.flip(image, 1)
                cv2.circle(image, (x,y), 8, (0,0,0))
                image = cv2.flip(image, 0)
                image = cv2.flip(image, 1)
            
            height, width, channel = image.shape
            bytes_per_line = 3 * width
            image = cv2.flip(image, 0)
            image = cv2.flip(image, 1)
            qt_image = QImage(image.data, width, height, bytes_per_line, QImage.Format_BGR888)
            self.video_frame.setPixmap(QPixmap.fromImage(qt_image))
        
        except Exception as e:
            self.display_message(f"Video Feed Error: {e}")

    def closeEvent(self, event):
        arduino.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = OAK_GUI()
    gui.show()
    sys.exit(app.exec_())