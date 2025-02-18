FROM python:3.9-slim

# Set the working directory
WORKDIR /pylitterbot2mqtt

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Command to run the mqtt_client.py script
CMD ["python", "pylitterbot2mqtt.py"]
