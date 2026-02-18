import os, sys, io
import M5
from M5 import *
import network
import m5ui
import lvgl as lv
from unit import RFIDUnit
from hardware import I2C, Pin
import time
from umqtt.simple import MQTTClient
import esp32
from esp32 import NVS
import ujson
import utime
#from audio import Player
from machine import unique_id
import ubinascii
from unit import RGBUnit
import requests
import machine
#player = None
serial = ubinascii.hexlify(unique_id()).decode()
# Constants and Configuration
#WIFI_SSID = 'UI-Matrix'
#WIFI_PASS = 'Uimatrix01'
WIFI_SSID = 'Utopia-WiFi'
WIFI_PASS = '@!nt3lGwn#1'
#WIFI_SSID = 'EHTISHAM'
#WIFI_PASS = '123456789'
#WIFI_SSID = 'okay.'
#WIFI_PASS = '125125125'
#WIFI_SSID = 'StormFiber-2.4G'
#WIFI_PASS = '22733801'

import requests
import machine

nvs = esp32.NVS("storage")

def get_local_version():
    try:
        return nvs.get_str("fw_version")
    except:
        return "1.0"   # default first install

def set_local_version(version):
    try:
        nvs.set_str("fw_version", version)
        nvs.commit()
        print("Version saved:", version)
    except Exception as e:
        print("NVS save error:", e)

local_version = get_local_version()

def check_for_update():
    try:
        print("Checking for update...")

        r = requests.get(UPDATE_VERSION_URL)
        remote_version = r.text.strip()
        r.close()

        print("Remote:", remote_version)
        print("Local :", local_version)

        if float(remote_version) > float(local_version):
            print("New version found. Updating...")

            r = requests.get(UPDATE_FILE_URL)
            new_code = r.text
            r.close()

            with open("/flash/main_ota_temp.py", "w") as f:
                f.write(new_code)

            print("Update downloaded. Restarting...")
            machine.reset()

        else:
            print("Already latest version")

    except Exception as e:
        print("Update check failed:", e)


UPDATE_VERSION_URL = "https://raw.githubusercontent.com/husbananjum/m5core-s3-firmware/refs/heads/main/version.txt"
UPDATE_FILE_URL = "https://raw.githubusercontent.com/husbananjum/m5core-s3-firmware/refs/heads/main/main.py"


MQTT_CLIENT_ID = serial
MQTT_BROKER = '192.168.15.5'
MQTT_PORT = 1883
MQTT_USER = 'utopia'
MQTT_PASSWORD = 'utopia01'
MQTT_RESET_TOPIC = 'reset-topic'
RESET_UID = "D3:58:24:F8:00:00:00:00:00:00"
NVS_NAMESPACE = "rfid_data"
MAX_RETRIES = 5
MQTT_TOPIC = "send_receive_data123"
MQTT_LAMP = "lamp_topic"
DEVICE_TYPE = "tag_reader"
DEVICE_NUMBER = serial
MQTT_RESPONSE_DATA = 'response_data'
# UI Elements
ui_elements = {
    'label3': None,  # Last UID display
    'label4': None,  # IP address
    'label5': None,  # Card present status
    'label6': None,  # Current UID
    'title0': None,  # Title
    'label7': None,  # "PROD COUNT:" label
    'label8': None,  # Product counter
    'label1': None,  # "TAG UID:" label
    'line0': None,    # Divider line
    'image1': None,
    'label9': None, # Operator ID
    'label10': None, #MSG
    'label2': None,
    'rect0': None,
    'rect1': None ,
    'rect2': None,
     'rect3':None,
     'rect4':None,
    'image0': None,
    'image1': None,
    'image2': None,
    'image3': None,
    'image4': None,
    'image5': None,
    'image6': None,
    'bettery_per': None,
    'charging_icon':None
}
bettery_icon = None
card=0  # card insert=1 card not insert =0
rfid_re_init=0
# System Components
wlan = None
i2c0 = None
rfid_0 = None
rgb_0=None
mqtt_client = None
Operator_ID = "-"
lamp_color = 0 
tag_counter = 0
seen_uids = set()
wifi_retry_count = 0
last_uid_str= "-"
# --- NEW GLOBALS FOR ACK WAIT ---
waiting_for_ack = False
ack_deadline = 0
# --------------------------------
def read_all_fields():
    lengths = [4, 5, 6, 8, 9, 10, 12]
    values = []
    for length in lengths:
        try:
            value = rfid_0.read(length).decode('utf-8').strip('\x00')
        except:
            value = None
        values.append(value)
    return tuple(values)
def get_datetime():
    """Get current datetime in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)"""
    now = utime.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        now[0], now[1], now[2], now[3], now[4], now[5])
def safe_label_update(label, text):
    """Safely update label text if label exists"""
    if label is not None:
        label.setText(str(text))
def load_from_nvs():
    global tag_counter, seen_uids, Operator_ID,lamp_color
    
    try:
        nvs = NVS(NVS_NAMESPACE)
        # Load tag counter
        try:
            tag_counter = nvs.get_i32("count")
        except:
            tag_counter = 0
            nvs.set_i32("count", tag_counter)
            nvs.commit()
        
        # Load last UID
        try:
            lamp_color = nvs.get_i32("color")
            print(f" load from nvs {lamp_color}")
        except:
            lamp_color = 0x008000
            nvs.set_i32("color", lamp_color)
            nvs.commit()
            
        # Load seen UIDs
        try:
            uid_count = nvs.get_i32("uid_count")
            seen_uids = set()
            for i in range(uid_count):
                uid_key = f"uid_{i}"
                seen_uids.add(nvs.get_str(uid_key))
        except:
            seen_uids = set()
            nvs.set_i32("uid_count", 0)
            nvs.commit()
            
        # Load Operator ID
        try:
            Operator_ID = nvs.get_str("operator_id")
            if Operator_ID == "" or Operator_ID == "NA":
                Operator_ID = "-"
        except:
            Operator_ID = "-"
            nvs.set_str("operator_id", Operator_ID)
            nvs.commit()
            
        # Update UI with loaded values
        safe_label_update(ui_elements['label8'], str(tag_counter))
        #safe_label_update(ui_elements['label3'], f"Last UID: {last_uid_str}")
        safe_label_update(ui_elements['label9'], str(Operator_ID))
        
    except Exception as e:
        print("NVS Load Error:", e)
        tag_counter = 0
        lamp_color = 0x008000
        seen_uids = set()
        Operator_ID = "-"
def save_to_nvs():
    global lamp_color  
    try:
        nvs = NVS(NVS_NAMESPACE)
        nvs.set_i32("count", tag_counter)
        nvs.set_i32("color", lamp_color)
        print(f"save to nvs {lamp_color}")
        nvs.set_str("operator_id", Operator_ID)
        
        # Save seen UIDs
        nvs.set_i32("uid_count", len(seen_uids))
        for i, uid in enumerate(seen_uids):
            nvs.set_str(f"uid_{i}", uid)
            
        nvs.commit()
    except Exception as e:
        print("NVS Save Error:", e)
def publish_rfid_data(sku, color, size, article, remarks, uid, count, cardtype, Operator_ID, serial):
    """Publish RFID data as JSON message with datetime timestamp"""
    global waiting_for_ack
    if waiting_for_ack:
        print("Publish blocked (waiting for ACK)")
        return
    try:
        if mqtt_client:
            message = {
                "card_type": cardtype,
                "operator_id": Operator_ID,
                #"sku": sku,
                #"color": color,
                #"size": size,
                #"article": article,
                #"remarks": remarks,
                "device_type": DEVICE_TYPE,
                #"device_number": DEVICE_NUMBER,
                "uid": uid,
                #"count": count,
                #"timestamp": get_datetime(),
                "device_serial": serial
            }
            mqtt_client.publish(MQTT_TOPIC, ujson.dumps(message), qos=0)
    except Exception as e:
        print("MQTT Publish Error:", e)
        reconnect_mqtt()
def init_ui():
    """Initialize all UI elements with null checks"""
    try:
        Widgets.fillScreen(0xffffff)
        
        #employee ID
        ui_elements['rect0'] = Widgets.Rectangle(4, 101, 152, 55, 0x616161, 0xffffff)
        ui_elements['image1'] = Widgets.Image("/flash/res/img/emp.jpg", 5, 102, scale_x=1, scale_y=1)
        #Operator ID
        ui_elements['label9'] = Widgets.Label(str(Operator_ID), 60, 124, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
        #PRoduction Count / Sewing machine
        ui_elements['rect1'] = Widgets.Rectangle(160, 101, 155, 55, 0x616161, 0xffffff)
        ui_elements['image0'] = Widgets.Image("/flash/res/img/mach.jpg", 165, 102, scale_x=1, scale_y=1)
        ui_elements['label8'] = Widgets.Label(str(tag_counter), 220, 124, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
        #RESPONSE DATA MESSAGE
        ui_elements['rect2'] = Widgets.Rectangle(4, 160, 311, 25, 0x616161, 0xffffff)        
        ui_elements['label10'] = Widgets.Label("MSG : ", 8, 166, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu12)
        #RFID PRESENT TAG UID
        ui_elements['rect3'] = Widgets.Rectangle(4, 189, 311, 47, 0x616161, 0xffffff)
        ui_elements['image3'] = Widgets.Image("/flash/res/img/rfid-tag-log.jpg", 5, 190, scale_x=1, scale_y=0.9)
        ui_elements['label6'] = Widgets.Label("-", 60, 205, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu12)
        # Device Serial no
        ui_elements['rect4'] = Widgets.Rectangle(4, 47, 311, 50, 0x616161, 0xffffff)
        ui_elements['image4'] = Widgets.Image("/flash/res/img/bar_c.jpg", 5, 58, scale_x=1.2, scale_y=1.2)
        # WIFI & MQTT LOGO
        ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi.jpg", 149, 3, scale_x=0.9, scale_y=1)
        ui_elements['image5'] = Widgets.Image("/flash/res/img/mqtt_error.jpg", 104, 1, scale_x=1, scale_y=1)
        ui_elements['label4'] = Widgets.Label("IP: Connecting...", 205, 35, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu9)
        # Utopia Logo
        ui_elements['image6'] = Widgets.Image("/flash/res/img/Logo.jpg", 0, 0)
        
        # Bettery %
        ui_elements['bettery_per'] =Widgets.Label("b%", 230, 15,1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu12)
    except Exception as e:
        print("UI Init Error:", e)
def connect_wifi():
    global wlan, wifi_retry_count
    
    if not wlan.isconnected():
        try:
            safe_label_update(ui_elements['label4'], "WiFi: Connecting...")
            ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi_error.jpg", 150, 3, scale_x=1.1, scale_y=1)
            rgb_0.fill_color(0x0000FF)
            wlan.connect(WIFI_SSID, WIFI_PASS)
            
            # Wait for connection with timeout
            timeout = 10  # 20 seconds timeout
            while not wlan.isconnected() and timeout > 0:
                time.sleep_ms(500)
                timeout -= 0.5
                M5.update()
            
            if wlan.isconnected():
                ip_address = wlan.ifconfig()[0]
                safe_label_update(ui_elements['label4'], "IP:" + ip_address)
                ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi.jpg", 149, 3, scale_x=0.9, scale_y=1)
                rgb_0.fill_color(lamp_color)  
            else:
                safe_label_update(ui_elements['label4'], "WiFi: Timeout")
                ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi_error.jpg", 150, 3, scale_x=1.1, scale_y=1)
                rgb_0.fill_color(0x0000FF)
                wifi_retry_count += 1
                if wifi_retry_count < MAX_RETRIES:
                    time.sleep(2)
                    connect_wifi()
                
        except Exception as e:
            safe_label_update(ui_elements['label4'], "WiFi: Error")
            ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi_error.jpg", 150, 3, scale_x=1.1, scale_y=1)
            print("WiFi Error:", e)
            rgb_0.fill_color(0x0000FF)
            wifi_retry_count += 1
            if wifi_retry_count < MAX_RETRIES:
                time.sleep(2)
                connect_wifi()
def check_wifi():
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        safe_label_update(ui_elements['label4'], "IP:" + ip)
        ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi.jpg", 149, 3, scale_x=0.9, scale_y=1)
        rgb_0.fill_color(lamp_color)  
        
    else:
        print("WiFi not connected")
        rgb_0.fill_color(0x0000FF)
        safe_label_update(ui_elements['label4'], "WiFi: Disconnected")
        ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi_error.jpg", 150, 3, scale_x=1.1, scale_y=1)
        
def init_wifi():
    global wlan
    
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.config(reconnects=MAX_RETRIES)
        connect_wifi()
    except Exception as e:
        print("WiFi Init Error:", e)
        safe_label_update(ui_elements['label4'], "WiFi Error")
        ui_elements['image2'] = Widgets.Image("/flash/res/img/wifi_error.jpg", 150, 3, scale_x=1.1, scale_y=1)
        rgb_0.fill_color(0x0000FF)
        
def mqtt_callback(*args):
    """Universal callback that handles all MQTT library versions"""
    global tag_counter, seen_uids, last_uid_str, Operator_ID, output, ack, target_serial, data, lamp_color, waiting_for_ack
    
    try:
        # Determine callback signature based on args length
        if len(args) == 2:  # Standard umqtt.simple (topic, message)
            topic, msg = args
        elif len(args) == 4:  # Some variants (topic, msg, retained, duplicate)
            topic, msg, _, _ = args
        else:
            print("Unsupported callback format")
            return
            
        # Ensure proper string decoding
        topic = topic.decode('utf-8') if isinstance(topic, bytes) else topic
        msg = msg.decode('utf-8') if isinstance(msg, bytes) else msg
        
        print(f"MQTT: {topic} -> {msg}")
        
        
        if topic.endswith(MQTT_RESET_TOPIC) and msg.lower() == 'reset':
            # Reset all counters and data
            seen_uids.clear()
            tag_counter = 0
            last_uid_str = "-"
            #Operator_ID = "-"
            
            # Update UI
            safe_label_update(ui_elements['label8'], "0")
            safe_label_update(ui_elements['label3'], "Last UID: - (Reset)")
            #safe_label_update(ui_elements['label9'], "-") #Label for Operator ID
            safe_label_update(ui_elements['label6'], "-")
            safe_label_update(ui_elements['label10'], "MSG : ")
            
            # Persist state
            save_to_nvs()
            print("System reset via MQTT")
        if topic.endswith(MQTT_RESPONSE_DATA):
          try:
            data = ujson.loads(msg)  # decode JSON payload
            target_serial = data.get("device_serial")
            ack = data.get("ack")
            output=data.get("output")
           # Only act if the message is for THIS device
            print(f"target sr= {target_serial}")
            if target_serial == serial and ack == 1:
              # ACK received for this device
              waiting_for_ack = False
              print(output)
              tag_counter += 1
              safe_label_update(ui_elements['label8'], tag_counter)
              safe_label_update(ui_elements['label10'], f"MSG : {output}")
              save_to_nvs()
            elif target_serial == serial and ack == 0:
              # Negative ACK but still targeted to this device
              waiting_for_ack = False
              safe_label_update(ui_elements['label10'], f"MSG : {output}")
              print(output)
            else:
              print("Message ignored, condition does not match")
              #safe_label_update(ui_elements['label10'], f"MSG : ")
          except Exception as e:
            print("response data error:", e)
        if topic.endswith(MQTT_LAMP):
          try:
              data = ujson.loads(msg)  # decode JSON payload
              target_serial = data.get("serial")
              color = data.get("color")
              # Only act if the message is for THIS device
              if target_serial == serial:
                  # Clear waiting flag if message is specifically for this device
                  waiting_for_ack = False
                  if color == "red":
                      print("Set light RED")
                      rgb_0.fill_color(0xff0000)
                      lamp_color = 0xff0000
                      save_to_nvs()
                  elif color == "green":
                      print("Set light GREEN")
                      rgb_0.fill_color(0x008000)
                      lamp_color = 0x008000
                      save_to_nvs()
                  elif color == "yellow":
                      print("Set light yellow")
                      rgb_0.fill_color(0xffff00)
                      lamp_color = 0xffff00
                      save_to_nvs()
                  elif color == "purple":
                      print("Set light purple")
                      rgb_0.fill_color(0x800080)
                      lamp_color = 0x800080
                      save_to_nvs()
                  elif color == "blue":
                      print("Set light blue")
                      rgb_0.fill_color(0x0000FF)
                      lamp_color = 0x0000FF
                      save_to_nvs()
                  else:
                      pass
              else:
                  print("Message ignored, serial does not match")
          except Exception as e:
              print("QC-status topic parse error:", e)
    except Exception as e:
        print("MQTT Callback Error:", e)
def init_mqtt():
    global mqtt_client
    rgb_0.fill_color(0x0000FF)
    
    try:
        if not wlan.isconnected():
            safe_label_update(ui_elements['label4'], "WiFi Disconnected")
            rgb_0.fill_color(0x0000FF)
            return
            
        # Initialize MQTT client with shorter timeout
        mqtt_client = MQTTClient(
            client_id=MQTT_CLIENT_ID,
            server=MQTT_BROKER,
            port=MQTT_PORT,
            user=MQTT_USER,
            password=MQTT_PASSWORD,
            keepalive=30,
            ssl=False
        )
        
        # Set the universal callback
        mqtt_client.set_callback(mqtt_callback)
        
        # Connect with clean session
        mqtt_client.connect(clean_session=True)
        
        # Subscribe to reset topic
        mqtt_client.subscribe(MQTT_RESET_TOPIC)
        mqtt_client.subscribe(MQTT_RESPONSE_DATA)
        mqtt_client.subscribe(MQTT_LAMP)
        
        print(f"MQTT Connected to {MQTT_BROKER}")
        safe_label_update(ui_elements['label4'], f"IP:{wlan.ifconfig()[0]}")
        ui_elements['image5'] = Widgets.Image("/flash/res/img/MQTT_Cloud.jpg", 100, 0, scale_x=1, scale_y=1)
        rgb_0.fill_color(lamp_color)  
        
    except Exception as e:
        print("MQTT Init Failed:", e)
        safe_label_update(ui_elements['label4'], "MQTT Error")
        ui_elements['image5'] = Widgets.Image("/flash/res/img/mqtt_error.jpg", 104, 1, scale_x=1, scale_y=1)
        rgb_0.fill_color(0x0000FF)
        mqtt_client = None  # Ensure clean state for reconnect
        connect_wifi()
        init_mqtt()
        print("MQTT RE-INITIALIZE SUCCESS")
def reconnect_mqtt():
    global mqtt_client
    rgb_0.fill_color(0x0000FF)
    print("RECONNECT MQTT")
    
    try:
        if mqtt_client:
            mqtt_client.disconnect()
        init_mqtt()
    except Exception as e:
        print("MQTT Reconnect Error:", e)
        safe_label_update(ui_elements['label4'], "MQTT Reconnect Err")
        ui_elements['image5'] = Widgets.Image("/flash/res/img/mqtt_error.jpg", 104, 1, scale_x=1, scale_y=1)
        rgb_0.fill_color(0x0000FF)
        
        #reconnect wifi
        connect_wifi()
        init_mqtt()
        print("MQTT RE-INITIALIZE SUCCESS")
def loop():
    global tag_counter, seen_uids, last_uid_str, mqtt_client, serial, player, Operator_ID ,battery_per , bettery_icon, card,rfid_re_init,i2c0,rfid_0,lamp_color, waiting_for_ack, ack_deadline
    
    #M5.update()
    serial = ubinascii.hexlify(unique_id()).decode()
    check_wifi()
    time.sleep(0.1)
    bettery_icon.set_value(Power.getBatteryLevel(), True)
    #bettery_per.set_text(f"{str(Power.getBatteryLevel())}%")
    safe_label_update(ui_elements['bettery_per'], str(Power.getBatteryLevel()))
    if Power.isCharging():
      ui_elements['charging_icon'] = Widgets.Image("/flash/res/img/charging.jpg", 305, 11)
    else:
      ui_elements['charging_icon'] = Widgets.Image("/flash/res/img/not_charging.jpg", 305,11)
    
    if not wlan.isconnected():
        connect_wifi()
        if wlan.isconnected():
          init_mqtt()
          print("MQTT RE-INITIALIZE SUCCESS")
        if not wlan.isconnected():
            time.sleep(1)
            return
    
    # Check for MQTT messages
    try:
        if mqtt_client:
            mqtt_client.check_msg()
    except:
        reconnect_mqtt()
        return
    
    # --- ACK TIMEOUT HANDLING (non-blocking) ---
    if waiting_for_ack:
        # utime.ticks_diff returns positive when now >= ack_deadline
        if utime.ticks_diff(utime.ticks_ms(), ack_deadline) >= 0:
            print("ACK TIMEOUT: No response received")
            safe_label_update(ui_elements['label10'], "MSG : NO RESPONSE RECIEVED")
            waiting_for_ack = False
    # ------------------------------------------------
    
    # RFID Processing
    try:
        if rfid_re_init==1:
          i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
          rfid_0 = RFIDUnit(i2c0)
          rfid_re_init=0
          print("RFID RE_INITIALIZED")
        else:
          pass
        card_present = rfid_0.is_new_card_present() if rfid_0 else False
        safe_label_update(ui_elements['label5'], card_present)
        if waiting_for_ack:
            # Show card is ignored during waiting
            if card_present:
                safe_label_update(ui_elements['label10'], "MSG : WAITING FOR RESPONSE")
            return
        
        if card_present:
            current_uid = rfid_0.read_card_uid() if rfid_0 else None
            if current_uid:
                
                # Convert UID bytearray to consistent string format
                uid_str = ':'.join(['%02X' % b for b in current_uid])
                safe_label_update(ui_elements['label6'], uid_str)
                # Read all fields from the card
                sku, color, size, article, remarks, cardtype, new_operator_id = read_all_fields()
                rfid_0.close()
                # Update Operator ID if we have a new valid ID
                if new_operator_id and new_operator_id != '0' and cardtype=='Operator' and card==0:
                    card=1
                    Operator_ID = new_operator_id
                    safe_label_update(ui_elements['label9'], str(Operator_ID))
                    # Save the new Operator ID immediately
                    save_to_nvs()
                    publish_rfid_data(sku, color, size, article, remarks, last_uid_str, tag_counter, cardtype, Operator_ID, serial)
                    # --- START WAIT FOR ACK (seconds) ---
                    safe_label_update(ui_elements['label10'], "MSG : WAITING FOR RESPONSE")
                    waiting_for_ack = True
                    ack_deadline = utime.ticks_add(utime.ticks_ms(), 10000)
                    # ---------------------------------------
                    #player.play_tone(2000, 0.04, volume=100, sync=True)
                    #player.play("file://flash/res/audio/beep.mp3", pos=0, volume=100, sync=True)
                #if uid_str == RESET_UID:
                if cardtype == "Reset":
                    # Reset logic
                    seen_uids.clear()
                    tag_counter = 0
                    last_uid_str = "-"
                    Operator_ID = "0"
                    safe_label_update(ui_elements['label8'], "0")
                    safe_label_update(ui_elements['label3'], "Last UID: - (Reset)")
                    safe_label_update(ui_elements['label9'], "-")
                    safe_label_update(ui_elements['label10'], "MSG : ")
                    save_to_nvs()
                    publish_rfid_data("RESET", "RESET", "RESET", "RESET", "RESET", "RESET", "RESET", "RESET", 0, serial)
                    # --- START WAIT FOR ACK (seconds) AFTER RESET ---
                    safe_label_update(ui_elements['label10'], "MSG : WAITING FOR RESPONSE")
                    waiting_for_ack = True
                    ack_deadline = utime.ticks_add(utime.ticks_ms(), 10000)
                    # ---------------------------------------
                    return
                
                # Update last UID shown
                last_uid_str = uid_str
                safe_label_update(ui_elements['label3'], f"Last UID: {last_uid_str}")
                
                #if uid_str not in seen_uids and cardtype == 'Product':
                if cardtype == 'Product' and card==0:
                    card=1  
                    #seen_uids.add(uid_str)
                    #if cardtype == 'Product':
                     #   tag_counter += 1
                    safe_label_update(ui_elements['label8'], str(tag_counter))
                    save_to_nvs()
                    publish_rfid_data(sku, color, size, article, remarks, last_uid_str, tag_counter, cardtype, Operator_ID, serial)
                    # --- START WAIT FOR ACK (seconds) ---
                    safe_label_update(ui_elements['label10'], "MSG : WAITING FOR RESPONSE")
                    waiting_for_ack = True
                    ack_deadline = utime.ticks_add(utime.ticks_ms(), 10000)
                    # ---------------------------------------
                    #player.play_tone(2000, 0.04, volume=100, sync=True)
                    #player.play("file://flash/res/audio/beep.mp3", pos=0, volume=100, sync=True)
        else:
            safe_label_update(ui_elements['label6'], "-")
            safe_label_update(ui_elements['label3'], f"Last UID: {last_uid_str}")
            card=0
        
        #mqtt_client.publish(f"M5devices/{DEVICE_NUMBER}", ujson.dumps({"online":"True","operator_id":f"{Operator_ID}","serial":f"{serial}"}), qos=0)
        if mqtt_client:
            mqtt_client.publish(f"M5devices/{DEVICE_NUMBER}", ujson.dumps({}), qos=0)
        
    except Exception as e:
        print("RFID Processing Error:", e)
        safe_label_update(ui_elements['label6'], "RFID Error")
        rfid_re_init=1
    
    M5.update()
    time.sleep(0.1)
def setup():
    global wlan, i2c0, rfid_0, mqtt_client, label2, player , battery_per , bettery_icon , rfid_re_init,rgb_0,lamp_color
    
    M5.begin()
    m5ui.init()
    bettery_icon = m5ui.M5Bar(x=256, y=7, w=49, h=25, min_value=0, max_value=100, value=25, bg_c=0x616161, color=0x21f398)
    #player = Player(None)
    rgb_0 = RGBUnit((8, 9), 10)
    
    load_from_nvs()
    print(lamp_color)
    #if lamp_color==16776960:
      #rgb_0.fill_color(0xffff00)
    
    #rgb_0.fill_color(lamp_color)  
    rgb_0.fill_color(0x0000FF)
    init_ui()
    label2 = Widgets.Label("SR:  LOADING...", 70, 70, 1.0,0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    init_wifi()
    if wlan.isconnected():
      check_for_update() #check update files from git hub

    serial = ubinascii.hexlify(unique_id()).decode()
    
    label2.setText("SR: " + serial)
    label2.setColor(0x000000, 0xffffff)
    
    # Initialize RFID reader
    try:
        i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
        rfid_0 = RFIDUnit(i2c0)
        rfid_re_init=0
    except Exception as e:
        print("RFID Init Error:", e)
        safe_label_update(ui_elements['label6'], "RFID Error")
        rfid_re_init=1
    
    # Initialize MQTT
    init_mqtt()
    #rgb_0.fill_color(0x33ff33)
if __name__ == '__main__':
    try:
        setup()
        while True:
            loop()
    except Exception as e:
        print("Main Error:", e)
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("Please update firmware")
