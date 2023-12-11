import cv2
import serial
import sys
import time
from roboflowoak import RoboflowOak
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QFrame, QTextEdit, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

# TODO:
#   - Update model to use new platform
#   - Integrate limit switches
#   - Make a calibration script
#   - Add "bounds" to pickup_sequence
#   - Create sorting script when we have bins

port = "/dev/ttyACM0"
baud_rate = 9600
command_delay = 1
arduino = serial.Serial(port, baud_rate)

machine_dimensions = [(0, 3.45), (0, 3.6), (0, 0.325)]
mmpp = [0.41, -0.41]
offsets = [150, 262]

def send_gcode(command):
    command = str.encode(command.strip() + '\n')
    arduino.write(command)
    response = arduino.readline()
    time.sleep(command_delay)
    return response.strip()

def pickup_sequence(x, y):
    # In the future we will check x,y against bounds of machine
    return [
        f"G01 x{((mmpp[0]*x)+offsets[0])/100} y{((mmpp[1]*y)+offsets[1])/100} f300",
        # f"G01 x{((mmpp[0]*x)+offsets[0])/100} f300",
        # f"G01 y{((mmpp[1]*y)+offsets[1])/100} f300",
        "M08",
        f"G01 z{machine_dimensions[2][1]} f300",
        "G01 z0 f300",
        "G01 x0 y0 f300",
        "M09"
    ]

class OAK_GUI(QMainWindow):

    def __init__(self, video_scale=1):
        super().__init__()

        # Initialize the AI, then the GUI
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

        print("Initializing UI...")
        self.initUI()

        self.display_message("RoboflowOak is " + ("active!" if self.roboflowoak_active else "inactive!"))
    
    def initUI(self):
        # Title the window
        self.setWindowTitle("Jelly Bean Sorter")

        # Create layouts
        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        button_layout = QVBoxLayout()
        table_layout = QVBoxLayout()

        # Create video view, add it to the top layout
        self.video_frame = QLabel()
        self.video_frame.setFixedSize(640*self.video_scale, 640*self.video_scale)
        self.video_frame.setFrameStyle(QFrame.Sunken | QFrame.Panel)
        top_layout.addWidget(self.video_frame)

        # Create buttons, add them to the button layout
        self.start_button = QPushButton("Start Video", self)
        self.start_button.setFixedSize(120, 60)
        self.start_button.clicked.connect(self.start_video)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Video", self)
        self.stop_button.setFixedSize(120, 60)
        self.stop_button.clicked.connect(self.stop_video)
        button_layout.addWidget(self.stop_button)

        self.snapshot_button = QPushButton("Snapshot", self)
        self.snapshot_button.setFixedSize(120, 60)
        self.snapshot_button.clicked.connect(self.snapshot)
        button_layout.addWidget(self.snapshot_button)

        self.action_button = QPushButton("Pick Flavor", self)
        self.action_button.setFixedSize(120, 60)
        self.action_button.clicked.connect(self.pick_flavor)
        button_layout.addWidget(self.action_button)

        self.auto_button = QPushButton("Auto Pick", self)
        self.auto_button.setFixedSize(120, 60)
        self.auto_button.clicked.connect(self.auto_pick)
        button_layout.addWidget(self.auto_button)

        # Create the predictions table
        self.predictions_table = QTableWidget()
        self.predictions_table.setColumnCount(3)
        self.predictions_table.setHorizontalHeaderLabels(['Flavor', 'Avg Confidence', 'Coordinates'])
        self.predictions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table_layout.addWidget(self.predictions_table)

        # Create message box
        self.message_box = QTextEdit()
        self.message_box.setReadOnly(True)

        # Combine layouts
        top_layout.addLayout(button_layout)
        top_layout.addLayout(table_layout)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.message_box)

        # Add everything to the central widget
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
        self.video_frame.clear()
        self.predictions_table.setRowCount(0)
    
    def snapshot(self):
        self.snapshot_mode = True
        self.video_running = False
        self.timer.stop()

    def pick_flavor(self):
        selected_flavor = self.predictions_table.selectedItems()[0].text()
        if selected_flavor:
            coords = self.flavor_coordinates.get(selected_flavor)
            if coords:
                x = abs(int(640-coords[0]))
                y = abs(int(640-coords[1]))

                gcode_commands = pickup_sequence(x,y)

                # "Wakes up" the serial on the arduino
                # May not be needed, further testing required
                send_gcode("Wakeup... or else...")
                time.sleep(2)

                self.display_message("Picking up: "+bean)
                for command in gcode_commands:
                    self.display_message("Sending:\t"+command)
                    send_gcode(command)
            else:
                self.display_message("That flavors coordinates don't exist!")
        else:
            self.display_message("No flavor selected!")

    def auto_pick(self):
        # Note, ghost beans are being detected, so bean count may be off
        # While beanz detected, pick them up, put them down at (0,0)
        while self.predictions_table.item(0,0):
            self.snapshot()
            bean = self.predictions_table.item(0,0).text()
            coords = self.predictions_table.item(0,2).text().split(",")
            gcode_commands = pickup_sequence(int(coords[0]), int(coords[1]))

            self.display_message("Picking up: "+bean)
            for command in gcode_commands:
                self.display_message("Sending:\t"+command)
                send_gcode(command)

            self.start_video()
            self.update_frame()

        send_gcode("G01 x0 y0 f300")
        return True
  
    def update_frame(self):
        if not self.video_running or "Video Feed Error" in self.last_message:
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
            
            flavor_stats = [(flavor, data['count'], data['total_confidence'] / data['count']) for flavor, data in flavors_data.items()]
            flavor_stats.sort(key=lambda x: (-x[2], -x[1]))

            self.predictions_table.setRowCount(len(flavor_stats))

            for i, (flavor, count, avg_conf) in enumerate(flavor_stats):
                # Add label to image
                coords = self.flavor_coordinates.get(flavor, ('N/A', 'N/A'))
                text_size = cv2.getTextSize(flavor, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
                x = abs(int(640-coords[0]))
                y = abs(int(640-coords[1]))

                # Add data to table
                self.predictions_table.setItem(i, 0, QTableWidgetItem(flavor))
                self.predictions_table.setItem(i, 1, QTableWidgetItem(f"{avg_conf:.2f}"))
                self.predictions_table.setItem(i, 2, QTableWidgetItem(f"{x}, {y}"))

                image = cv2.flip(image, 0)
                image = cv2.flip(image, 1)
                cv2.circle(image, (x,y), 8, (0,0,0))
                # cv2.putText(image, flavor, (x,y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2, cv2.LINE_AA)
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = OAK_GUI()
    gui.show()
    sys.exit(app.exec())
