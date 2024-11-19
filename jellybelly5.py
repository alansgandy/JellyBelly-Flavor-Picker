import depthai as dai
import numpy as np
import cv2

# Create a pipeline
pipeline = dai.Pipeline()

# Define source and output queues
camRgb = pipeline.createColorCamera()
camRgb.setBoardSocket(dai.CameraBoardSocket.CAM_A) # Addressing deprecation
camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
videoQueue = pipeline.createXLinkOut()
videoQueue.setStreamName("video")

nn = pipeline.createNeuralNetwork()
nn.setBlobPath("best_openvino_2022.1_6shave.blob")
nn.input.setBlocking(False)
nnQueue = pipeline.createXLinkOut()
nnQueue.setStreamName("nn")

# Linking nodes
camRgb.video.link(nn.input)
nn.out.link(nnQueue.input)
camRgb.video.link(videoQueue.input)

# Connect to device and start pipeline
with dai.Device(pipeline) as device:
    nnQueue = device.getOutputQueue("nn", 8, False)
    videoQueue = device.getOutputQueue("video", 8, False)

    while True:
        inNN = nnQueue.get()  # Retrieve the neural network results
        inRgb = videoQueue.get()  # Retrieve the video frame

        frame = inRgb.getCvFrame()
        resized_frame = cv2.resize(frame, (640, 640))  # Resize frame for NN
        
        # Display the frame
        cv2.imshow("Video", frame)
        
        # Note: The next section is a placeholder; you will need to update it based on your network's actual output.
        detections = inNN.getFirstLayerFp16()
        for detection in detections:
            print(detection)  # Temporary: To understand the structure of the output.
            # Please update the code below based on the printed structure.
            # x, y, w, h, class_id, confidence = detection
            # cv2.rectangle(frame, (int(x-w/2), int(y-h/2)), (int(x+w/2), int(y+h/2)), (0, 255, 0), 2)

        # Display the frame with detections
        cv2.imshow("Detections", frame)

        # Break on 'q' keypress
        if cv2.waitKey(1) == ord('q'):
            break
