import paho.mqtt.client as mqtt_client
import asyncio
import json
import os
from pylitterbot import Account, LitterRobot3, LitterRobot4, FeederRobot

LB2MQTT_BROKER = os.environ['LB2MQTT_BROKER']
LB2MQTT_USERNAME = os.environ['LB2MQTT_USERNAME']
LB2MQTT_PASSWORD = os.environ['LB2MQTT_PASSWORD']
LB2MQTT_PORT = int(os.environ['LB2MQTT_PORT'])
LB2MQTT_TOPIC_PREFIX = os.environ['LB2MQTT_TOPIC_PREFIX']
LB_USERNAME = os.environ['LB_USERNAME']
LB_PASSWORD = os.environ['LB_PASSWORD']

def connect_mqtt() -> mqtt_client:
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to MQTT Broker!")
        else:
            print(f"Failed to connect, return code %d\n", rc)

    client = mqtt_client.Client("litterbot")
    client.username_pw_set(LB2MQTT_USERNAME, LB2MQTT_PASSWORD)
    client.on_connect = on_connect
    client.connect(LB2MQTT_BROKER, LB2MQTT_PORT)
    return client


def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        print(f"Received message: topic: `{msg.topic}` payload:`{msg.payload.decode()}` ")
        asyncio.run(handle_message(client, msg))

    client.on_message = on_message
    client.subscribe(f"{LB2MQTT_TOPIC_PREFIX}/cmd/#")

async def handle_message(client, msg):
    topic_parts = msg.topic.split('/')
    if len(topic_parts) < 3:
        return

    command = topic_parts[2]
    print(f"command is: {command}")
        
    if (str(msg.payload.decode("utf-8")) != ""):
        payload = json.loads(msg.payload)

    account = Account()
    try:
        await account.connect(username=LB_USERNAME, password=LB_PASSWORD, load_robots=True, load_pets=True)
        if command == "get_robots":
            for robot in account.robots:
                client.publish(
                    f"{LB2MQTT_TOPIC_PREFIX}/robots/{robot.name}", 
                    json.dumps({
                    "model": robot.model, 
                    "serial": robot.serial,
                    "id": robot.id,
                    "online": robot.is_online,
                    "night_light_mode_enabled": robot.night_light_mode_enabled,
                    "panel_lock_enabled": robot.panel_lock_enabled,
                    "power_status": f"{robot.power_status}",
                    "setup_date": f"{robot.setup_date}",
                    }, 
                    ))
        if command == "get_pets":
            for pet in account.pets:
                client.publish(
                    f"{LB2MQTT_TOPIC_PREFIX}/pets/{pet.name}", 
                    json.dumps({
                    "id": pet.id,
                    "pet_type": f"{pet.pet_type}",
                    "gender": f"{pet.gender}",
                    "estimated_weight": pet.estimated_weight,
                    "last_weight_reading": pet.last_weight_reading,
                    "weight": pet.weight,
                    "birthday": f"{pet.birthday}",
                    "adoption_date": f"{pet.adoption_date}",
                    "diet": f"{pet.diet}",
                    "environment_type": f"{pet.environment_type}",
                    "health_concerns": json.dumps(pet.health_concerns),
                    "breeds": json.dumps(pet.breeds),
                    "image_url": f"{pet.image_url}",
                    "is_active": pet.is_active,
                    "is_fixed": pet.is_fixed,
                    "pet_tag_id": pet.pet_tag_id,
                    "weight_id_feature_enabled": pet.weight_id_feature_enabled,
                    }, 
                    ))
                weight_history = await pet.fetch_weight_history()
                for weighthist in weight_history:
                    client.publish(
                        f"{LB2MQTT_TOPIC_PREFIX}/pets/{pet.name}/weight-history", 
                        json.dumps({
                        f"{weighthist.timestamp}": f"{weighthist.weight}",
                        }, 
                        ))



# all the remaining messages require JSON Payload containing the id
        elif command == "refresh":
            await account.refresh_robots()
        elif command == "start_cleaning":
            robot_id = payload.get("robot_id")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.start_cleaning()
        elif command == "reset_settings":
            robot_id = payload.get("robot_id")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.reset_settings()
        elif command == "set_panel_lockout":
            robot_id = payload.get("robot_id")
            value = payload.get("value")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.set_panel_lockout(value)
        elif command == "set_night_light":
            robot_id = payload.get("robot_id")
            value = payload.get("value")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.set_night_light(value)
        elif command == "set_power_status":
            robot_id = payload.get("robot_id")
            value = payload.get("value")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.set_power_status(value)
        elif command == "set_sleep_mode":
            robot_id = payload.get("robot_id")
            value = payload.get("value")
            sleep_time = payload.get("sleep_time")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.set_sleep_mode(value, sleep_time)
        elif command == "set_wait_time":
            robot_id = payload.get("robot_id")
            wait_time = payload.get("wait_time")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.set_wait_time(wait_time)
        elif command == "set_name":
            robot_id = payload.get("robot_id")
            name = payload.get("name")
            robot = account.get_robot(robot_id)
            if robot:
                await robot.set_name(name)
        elif command == "get_activity_history":
            robot_id = payload.get("robot_id")
            limit = payload.get("limit", 100)
            robot = account.get_robot(robot_id)
            if robot:
                history = await robot.get_activity_history(limit)
                for data in history:
                    print(data)

#                client.publish(f"{LB2MQTT_TOPIC_PREFIX}/response", json.dumps(history))
        elif command == "get_insight":
            robot_id = payload.get("robot_id")
            days = payload.get("days", 30)
            timezone_offset = payload.get("timezone_offset")
            robot = account.get_robot(robot_id)
            if robot:
                insight = await robot.get_insight(days, timezone_offset)
                for data in insight:
                    print(insight)
#                client.publish(f"{LB2MQTT_TOPIC_PREFIX}/response", json.dumps(insight))

    finally:
        # Disconnect from the API.
        await account.disconnect()





def run():
    client = connect_mqtt()
    subscribe(client)
    client.loop_forever()

if __name__ == "__main__":
    run()
