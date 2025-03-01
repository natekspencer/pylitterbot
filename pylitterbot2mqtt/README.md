# pylitterbot2mqtt Project

## Overview
The pylitterbot2mqtt project is designed to interface with various robotic litter boxes and feeders using the MQTT protocol. This project allows users to control and monitor their devices through a simple MQTT client. It utlizes the Python libraries of pylitterbot.

## Files
- **Dockerfile**: Contains instructions to build a Docker image for the project.
- **pylitterbot2mqtt.py**: Implements the MQTT client that handles connections, message processing, and robot commands.
- **requirements.txt**: Lists the Python dependencies required for the project.

## Setup Instructions

### Prerequisites
- Docker must be installed on your machine.

### Building the Docker Image
To build the Docker image, navigate to the project directory and run the following command:

```
cd pylitter2mqtt
docker build -t pylitterbot2mqtt .
```

### Running the Docker Container
After building the image, you can run the container using:

```
docker run -d \
-e LB2MQTT_BROKER=mqtt.example.com \
-e LB2MQTT_PORT=1883 \
-e LB2MQTT_USERNAME=mqtt-user \
-e LB2MQTT_PASSWORD=mqtt-broker-password \
-e LB2MQTT_TOPIC_PREFIX=litterbox \
-e LB_USERNAME=cats@example.com \
-e LB_PASSWORD=litterbox-account-password \
-name pylb2mqtt pylitterbot2mqtt
```

## Usage
Once the container is running, the MQTT client will connect to the specified MQTT broker and listen for commands. You can publish messages to the appropriate topics to control your robots.

To Return information about your Litter Robot Products in your Account:
publish to "litterbot/cmd/get_robots" with an empty string payload (i.e "" )

the result will published to "litterbot/robots"

To Return information about your Pets in your Account:
pushish to "litterbot/cmd/get_pets" with an empty string payload (i.e "" )

the result will published to "litterbot/pets"

## Contributing
Contributions are welcome! Please feel free to submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.
