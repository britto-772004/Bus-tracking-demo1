from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading, time, math, random, requests
from geopy.distance import geodesic
from opencage.geocoder import OpenCageGeocode
import folium

app = Flask(__name__)
socketio = SocketIO(app)

# Global timer state
timer_state = {
    'remaining_time': 300,  # Default to 5 minutes in seconds
    'is_running': False
}

# To stop the timer thread
stop_timer_thread = False

# OpenCage API Key (Replace with your own API key)
OPENCAGE_API_KEY = 'd0912921b03b43ef94bf5cccb2194195'
OPENCAGE_URL = 'https://api.opencagedata.com/geocode/v1/json'

# In-memory storage for device locations
device_locations = {
    'device1': {'lat': None, 'lon': None},
    'device2': {'lat': None, 'lon': None}
}

# Static locations for Device 1 and Device 2
device_coordinates = {
    'device1': (11.0835, 76.9966),
    'device2': (11.4771273, 77.147258)
}

driver_location = None  # Global variable to store the driver's location

# KGISL Institute of Technology coordinates
kgisl_lat, kgisl_lng = 11.085489824665183, 76.9960311695961

# Store student locations
student_locations = []

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/driver')
def driver():
    return render_template('driver.html')

@app.route('/student')
def student():
    return render_template('student.html')

@app.route('/view_map')
def view_map():
    return render_template('starttrack_student.html')

@app.route('/geo_fencing')
def geo_fencing():
    students_count = 0
    mymap = folium.Map(location=[kgisl_lat, kgisl_lng], zoom_start=15)

    folium.Circle(
        radius=20,
        location=[kgisl_lat, kgisl_lng],
        color='blue',
        fill=True,
        fill_opacity=0.2
    ).add_to(mymap)

    for student in student_locations:
        if is_within_geofence(student['lat'], student['lng'], kgisl_lat, kgisl_lng):
            color = 'green'
        else:
            color = 'red'
            students_count += 1
        folium.Marker(
            location=[student['lat'], student['lng']],
            icon=folium.Icon(color=color)
        ).add_to(mymap)

    map_html = mymap._repr_html_()
    return render_template('map.html', map_html=map_html, students_count=students_count)

@app.route('/add_student_location', methods=['POST'])
def add_student_location():
    data = request.get_json()
    lat = data['lat']
    lng = data['lng']
    student_locations.append({'lat': lat, 'lng': lng})
    return jsonify({'status': 'success'})

@app.route('/count_students', methods=['GET'])
def count_students():
    count = sum(1 for student in student_locations if is_within_geofence(student['lat'], student['lng'], kgisl_lat, kgisl_lng))
    return jsonify({'count': count})

@app.route('/update_distances')
def update_distances():
    static_point = {'lat': 37.7749, 'lon': -122.4194}
    points = [
        {'lat': 37.774931 + random.uniform(-0.0001, 0.0001), 'lon': -122.419288 + random.uniform(-0.0001, 0.0001)}
        for _ in range(5)
    ]

    points_in_meters = [round(haversine(static_point['lat'], static_point['lon'], p['lat'], p['lon']), 2) for p in points]

    flag = all(distance <= 20 for distance in points_in_meters)

    if flag:
        message = "All students are near to the bus"
        color = 'green'
    else:
        message = "Some students are away from the bus"
        color = 'red'

    return jsonify({'points': points_in_meters, 'message': message, 'color': color})

@app.route('/start_tracking')
def start_tracking():
    return render_template('starttrack.html')

@app.route('/driver_location')
def driver_location():
    global driver_location
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    driver_location = (lat, lon)
    return jsonify({'driver': driver_location})

@app.route('/coordinates')
def coordinates():
    data = {
        'device1': device_coordinates['device1'],
        'device2': device_coordinates['device2']
    }
    if driver_location:
        data['driver'] = driver_location
    return jsonify(data)

@socketio.on('start_timer')
def handle_start_timer():
    global timer_state, stop_timer_thread
    if not timer_state['is_running']:
        timer_state['is_running'] = True
        stop_timer_thread = False
        thread = threading.Thread(target=countdown)
        thread.start()
    emit('timer_update', timer_state, broadcast=True)

@socketio.on('stop_timer')
def handle_stop_timer():
    global timer_state, stop_timer_thread
    timer_state['is_running'] = False
    stop_timer_thread = True
    emit('timer_update', timer_state, broadcast=True)

@socketio.on('reset_timer')
def handle_reset_timer():
    global timer_state, stop_timer_thread
    timer_state['remaining_time'] = 300  # Reset to 5 minutes
    timer_state['is_running'] = False
    stop_timer_thread = True
    emit('timer_update', timer_state, broadcast=True)

@socketio.on('set_time')
def handle_set_time(data):
    global timer_state, stop_timer_thread
    timer_state['remaining_time'] = data['new_time']
    timer_state['is_running'] = False
    stop_timer_thread = True
    emit('timer_update', timer_state, broadcast=True)

def countdown():
    global timer_state, stop_timer_thread
    while timer_state['is_running'] and timer_state['remaining_time'] > 0 and not stop_timer_thread:
        time.sleep(1)
        timer_state['remaining_time'] -= 1
        if timer_state['remaining_time'] <= 30:
            socketio.emit('beep')
        if timer_state['remaining_time'] == 0:
            timer_state['is_running'] = False
            socketio.emit('beep')
        socketio.emit('timer_update', timer_state)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of the Earth in kilometers
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_km = R * c
    distance_m = distance_km * 1000  # Convert to meters
    return distance_m

def is_within_geofence(device_lat, device_lng, kgisl_lat, kgisl_lng, radius=1000):
    distance = geodesic((kgisl_lat, kgisl_lng), (device_lat, device_lng)).meters
    return distance <= radius

def reverse_geocode(lat, lon):
    params = {
        'key': OPENCAGE_API_KEY,
        'q': f'{lat},{lon}',
        'pretty': 1
    }
    response = requests.get(OPENCAGE_URL, params=params)
    data = response.json()
    if data['results']:
        return data['results'][0]['formatted']
    else:
        return "Address not found"

if __name__ == '__main__':
    socketio.run(app, debug=False,host='0.0.0.0')
