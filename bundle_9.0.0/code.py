# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
#
# AIO_weather_repeater_v00.py
# An AIO+ Weather Repeater for ESP32-S3 Feather

import board
import digitalio
import os
import time
import json
import ssl
import supervisor
import neopixel
import adafruit_datetime
import adafruit_connection_manager
import wifi
import adafruit_requests
import adafruit_minimqtt.adafruit_minimqtt as mqtt
from adafruit_io.adafruit_io import IO_MQTT
from cedargrove_temperaturetools.unit_converters import celsius_to_fahrenheit

from weatherkit_to_weathmap_icon import kit_to_map_icon

# Set default display brightness
board.DISPLAY.brightness = 0.025

# Instantiate the LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

# Initialize NeoPixel
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.01)
pixel[0] = 0xFFFF00  # Initializing (yellow)

# Get weather observations from the Sea-Tac station (47.45,-122.31)
W_TOPIC_KEY = 2730  # Integer value
W_TOPIC_DESC = "Seattle, WA"


def subscribe(client, userdata, topic, granted_qos):
    """Callback method for when the client subscribes to a new feed."""
    print(f"  ... subscribed to '{topic}' with QOS level {granted_qos}")


def message(client, feed_id, payload):
    """Callback method for when a subscribed feed has a new value."""
    global weather_data
    # print(payload)
    if feed_id == "weather":
        weather_data = json.loads(payload)


def wind_direction(heading):
    if heading is None:
        return '--'
    return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][int(((heading + 22.5) % 360) / 45)]


def publish_to_aio(value, feed):
    """Publish a value to an AIO feed at a throttled transaction rate. A
    blocking method.
    :param union(integer, float, string) value: The value to publish.
    :param string feed: The name of the AIO feed."""
    if value is not None:
        time.sleep(2.5)  # Until throttle method is re-enabled
        try:
            aio.publish(feed, value)
            pixel[0] = 0x00FF00  # Success (green)
            print(f"  ... SUCCESS: published '{value}' to AIO '{feed}'")
        except Exception as aio_publish_error:
            pixel[0] = 0xFF0000  # Error (red)
            print(f"  FAILED to publish '{value}' to AIO '{feed}'")
            print(f"    publish error: {str(aio_publish_error)}")

            print("attempting to reconnect to AIO...")
            try:
                aio.reconnect()
                pixel[0] = 0x00FF00  # Success (green)
            except Exception as pub_reconnect_error:
                pixel[0] = 0xFF0000  # Error (red)
                print(f"  FAILED: publish aio.reconnect {str(pub_reconnect_error)}")
                print("      MCU will soft reset in 60 seconds.")
                time.sleep(60)
                supervisor.reload()  # soft reset: keeps the terminal session alive

    else:
        print(f"  FAILED to publish '{value}' to AIO '{feed}'")


def busy(delay):
    """An alternative time.sleep function that blinks the LED once per second.
    A blocking method."""
    pixel[0] = 0x000000  # Normal (black)
    for blinks in range(int(round(delay, 0))):
        led.value = True
        time.sleep(0.05)
        led.value = False
        time.sleep(0.95)

try:
    # Connect to Wi-Fi access point
    print(f"Connecting to {os.getenv('CIRCUITPY_WIFI_SSID')}")
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD")
    )
    pixel[0] = 0x00FF00  # Success (green)
    print("  SUCCESS: connected to WiFi access point")
except Exception as wifi_access_error:
    pixel[0] = 0xFF0000  # Error (red)
    print(f"  FAILED: connect to WiFi. Error: {wifi_access_error}")
    print("      MCU will soft reset in 60 seconds.")
    time.sleep(60)
    supervisor.reload()  # soft reset: keeps the terminal session alive

# Initialize a requests session
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# Connect to AIO and MQTT
# Initialize the MQTT Client object (keep_alive default is 300 sec)
mqtt_client = mqtt.MQTT(
    broker="io.adafruit.com",
    username=os.getenv("aio_username"),
    password=os.getenv("aio_key"),
    keep_alive=180,
    socket_pool=pool,
    ssl_context=ssl.create_default_context(),
)

# Initialize AIO MQTT helper and connect to AIO
aio = IO_MQTT(mqtt_client)
print("  ... IO MQTT helper initialized")
aio.connect()
print(f"  ... IO MQTT connected: {mqtt_client.is_connected()}")

# Connect the callback methods to AIO
aio.on_subscribe = subscribe
aio.on_message = message

# Subscribe to the AIO+ weather topic
aio.subscribe_to_weather(W_TOPIC_KEY, "current")

# Initialize the weather_data and history variables
weather_data = None
weather_data_old = None

while True:
    # Fetch and update the weather conditions from AIO
    try:
        pixel[0] = 0xFFFF00  # AIO in progress (yellow)
        time.sleep(2.5)  # Until throttle method is re-enabled
        aio.loop(10)
        pixel[0] = 0x00FF00  # Success (green)
    except Exception as loop_error:
        pixel[0] = 0xFF0000  # Error (red)
        print(f"  FAILED: aio.loop {str(loop_error)}")
        print("    attempting to reconnect to AIO")
        try:
            time.sleep(10)
            aio.connect()
            pixel[0] = 0x00FF00  # Success (green)
        except Exception as loop_reconnect_error:
            pixel[0] = 0xFF0000  # Error (red)
            print(f"  FAILED: loop aio.reconnect {str(loop_reconnect_error)}")
            print("      MCU will soft reset in 60 seconds.")
            time.sleep(60)
            supervisor.reload()  # soft reset: keeps the terminal session alive

    if weather_data:
        if weather_data != weather_data_old:
            weatherkit_desc = weather_data["conditionCode"]
            weatherkit_temp = celsius_to_fahrenheit(weather_data["temperature"])
            weatherkit_humid = weather_data["humidity"] * 100
            weatherkit_wind_speed = weather_data["windSpeed"] * 0.6214
            weatherkit_wind_dir = wind_direction(weather_data["windDirection"])
            weatherkit_wind_gusts = weather_data["windGust"] * 0.6214
            weatherkit_timestamp = weather_data["metadata"]["readTime"]
            weatherkit_daylight = weather_data["daylight"]
            # print("daylight", weatherkit_daylight, type(weatherkit_daylight), dir(weatherkit_daylight))

            print("-" * 13 + " NEW " + "-" * 13)
            print(f"timestamp: {weatherkit_timestamp}")

            sample_time = adafruit_datetime.datetime.fromisoformat(weatherkit_timestamp[:-1])
            print(f"sample_time: {sample_time}")

            local_time = sample_time - adafruit_datetime.timedelta(hours=7)
            print(f"local_time: {local_time}")

            try:
                if weatherkit_daylight:
                    icon = kit_to_map_icon[weatherkit_desc][1] + "d"
                else:
                    icon = kit_to_map_icon[weatherkit_desc][1] + "n"
                long_desc = kit_to_map_icon[weatherkit_desc][0]
            except KeyError as desc_error:
                print(f"  NO Description: {desc_error}")
                icon = "99d"
                long_desc = f"unknown description: {weatherkit_desc}"
            print(f"icon: {icon}")
            print(f"long_description: {long_desc}")

            publish_to_aio(int(round(time.monotonic() / 60, 0)), "system-watchdog")
            publish_to_aio(weatherkit_desc, "weather-description")
            publish_to_aio(weatherkit_humid, "weather-humidity")
            publish_to_aio(weatherkit_temp, "weather-temperature")
            publish_to_aio(weatherkit_wind_dir, "weather-winddirection")
            publish_to_aio(weatherkit_wind_gusts, "weather-windgusts")
            publish_to_aio(weatherkit_wind_speed, "weather-windspeed")
            publish_to_aio(str(weatherkit_daylight), "weather-daylight")

            weather_data_old = weather_data  # to watch for changes
        busy(120)  # Delay for two minutes to reduce query rate
    else:
        print(f"  ... waiting for weather observations from {W_TOPIC_DESC}")
        busy(10)  # Step up query rate when first starting
