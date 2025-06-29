from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import bcrypt
from datetime import datetime, timedelta
from functools import wraps

# Inisialisasi Aplikasi Flask
app = Flask(__name__)
app.secret_key = 'kunci_rahasia_yang_sangat_aman_dan_unik_untuk_proyek_ini'

# Koneksi ke Database MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['flight_booking_db']

# Inisialisasi Koleksi (Tabel)
users_collection = db['users']
flights_collection = db['flights']
bookings_collection = db['bookings']

# =======================================================================
# FUNGSI HELPER & DECORATOR
# =======================================================================

def hash_password(password):
    """Fungsi untuk mengenkripsi password."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, password):
    """Fungsi untuk memverifikasi password."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def admin_required(f):
    """Decorator untuk membatasi akses hanya untuk admin."""
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Anda tidak memiliki izin untuk mengakses halaman ini.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

# =======================================================================
# RUTE UNTUK PENGGUNA UMUM (USER)
# =======================================================================

@app.route('/')
def index():
    """Menampilkan halaman utama (Beranda)."""
    now = datetime.now()
    query = {
        'departure_time': {'$gt': now},
        'available_seats': {'$gt': 0}
    }
    available_flights = list(flights_collection.find(query).sort('departure_time', 1).limit(7))
    return render_template('index.html', flights=available_flights)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Menangani registrasi pengguna baru."""
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if users_collection.find_one({'$or': [{'username': username}, {'email': email}]}):
            flash('Username atau Email sudah terdaftar!', 'error')
            return redirect(url_for('register'))
        hashed_pass = hash_password(password)
        users_collection.insert_one({
            'name': name, 'username': username, 'password': hashed_pass, 
            'email': email, 'role': 'user', 'created_at': datetime.now()
        })
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Menangani proses login untuk pengguna dan admin."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Login khusus untuk admin
        if username == "admin" and password == "admin123":
            session['user_id'] = "admin_hardcoded_id"
            session['username'] = "admin"
            session['role'] = "admin"
            flash('Selamat datang Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        
        # Login untuk pengguna biasa
        user = users_collection.find_one({'username': username})
        if user and check_password(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user.get('role', 'user')
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Menangani proses logout."""
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('index'))

@app.route('/search_flights', methods=['GET'])
def search_flights():
    """Menampilkan hasil pencarian penerbangan berdasarkan kriteria."""
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    departure_date_str = request.args.get('departure_date')
    if not all([origin, destination, departure_date_str]):
        flash('Harap lengkapi semua field pencarian.', 'error')
        return redirect(url_for('index'))
    try:
        departure_date = datetime.strptime(departure_date_str, '%Y-%m-%d')
        end_of_day = departure_date + timedelta(days=1)
    except (ValueError, TypeError):
        flash('Format tanggal tidak valid.', 'error')
        return redirect(url_for('index'))
    query = {
        'origin_airport': origin.upper(), 'destination_airport': destination.upper(),
        'departure_time': {'$gte': departure_date, '$lt': end_of_day},
        'available_seats': {'$gt': 0}
    }
    flights = list(flights_collection.find(query).sort('departure_time', 1))
    return render_template('search.html', flights=flights)

@app.route('/search_by_code', methods=['POST'])
def search_by_code():
    """Mencari penerbangan berdasarkan kode dan redirect ke halaman booking."""
    flight_code = request.form.get('flight_code')
    if not flight_code:
        flash('Silakan masukkan kode penerbangan.', 'error')
        return redirect(url_for('index'))
    flight = flights_collection.find_one({'flight_number': flight_code.upper()})
    if flight:
        return redirect(url_for('book_flight', flight_id=str(flight['_id'])))
    else:
        flash(f'Penerbangan dengan kode "{flight_code}" tidak ditemukan.', 'error')
        return redirect(url_for('index'))
    
@app.route('/all_flights')
def all_flights():
    """Menampilkan semua jadwal penerbangan yang tersedia."""
    flights = list(flights_collection.find({'departure_time': {'$gt': datetime.now()}}).sort('departure_time', 1))
    return render_template('all_flights.html', flights=flights)

@app.route('/book_flight/<flight_id>', methods=['GET', 'POST'])
def book_flight(flight_id):
    """Menampilkan halaman booking dan memproses pemesanan."""
    if 'user_id' not in session:
        flash('Silakan login untuk memesan penerbangan.', 'error')
        return redirect(url_for('login'))

    flight = flights_collection.find_one({'_id': ObjectId(flight_id)})
    if not flight:
        flash('Penerbangan tidak ditemukan.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            num_tickets = int(request.form.get('num_tickets'))
        except (ValueError, TypeError):
            flash('Jumlah tiket tidak valid.', 'error')
            return redirect(url_for('book_flight', flight_id=flight_id))

        if num_tickets > flight.get('available_seats', 0):
            flash('Jumlah tiket melebihi kursi yang tersedia.', 'error')
            return redirect(url_for('book_flight', flight_id=flight_id))
            
        passengers_data = []
        for i in range(1, num_tickets + 1):
            passenger_name = request.form.get(f'passenger_name_{i}')
            passenger_id = request.form.get(f'passenger_id_number_{i}')
            if not passenger_name or not passenger_id:
                flash(f'Harap lengkapi data untuk Penumpang {i}.', 'error')
                return redirect(url_for('book_flight', flight_id=flight_id))
            passengers_data.append({'name': passenger_name, 'id_number': passenger_id})
            
        new_available_seats = flight.get('available_seats', 0) - num_tickets
        flights_collection.update_one(
            {'_id': ObjectId(flight_id)},
            {'$set': {'available_seats': new_available_seats}}
        )
        
        booking_data = {
            'user_id': ObjectId(session['user_id']), 'flight_id': ObjectId(flight_id),
            'booking_date': datetime.now(), 'number_of_tickets': num_tickets,
            'total_price': num_tickets * flight.get('price', 0), 'passengers': passengers_data,
            'status': 'confirmed'
        }
        bookings_collection.insert_one(booking_data)

        flash('Pemesanan berhasil!', 'success')
        return redirect(url_for('booking_history'))

    return render_template('booking.html', flight=flight)

@app.route('/booking_history')
def booking_history():
    """Menampilkan riwayat pemesanan pengguna."""
    if 'user_id' not in session or session.get('role') != 'user':
        flash('Silakan login sebagai pengguna untuk melihat riwayat.', 'error')
        return redirect(url_for('login'))
    user_bookings = list(bookings_collection.find({'user_id': ObjectId(session['user_id'])}).sort('booking_date', -1))
    detailed_bookings = []
    for booking in user_bookings:
        flight = flights_collection.find_one({'_id': booking['flight_id']})
        booking['flight_details'] = flight if flight else {}
        detailed_bookings.append(booking)
    return render_template('history.html', bookings=detailed_bookings)

# =======================================================================
# RUTE UNTUK PANEL ADMIN
# =======================================================================

@app.route('/admin_dashboard')
@admin_required 
def admin_dashboard():
    """Menampilkan dashboard utama admin."""
    total_flights = flights_collection.count_documents({})
    total_users = users_collection.count_documents({})
    total_bookings = bookings_collection.count_documents({})
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    this_month_start = today.replace(day=1)
    pipeline = [{"$match": {"booking_date": {"$gte": this_month_start}}}, {"$group": {"_id": None, "total_price": {"$sum": "$total_price"}}}]
    sales_result = list(bookings_collection.aggregate(pipeline))
    this_month_sales = sales_result[0]['total_price'] if sales_result else 0
    
    return render_template('admin_dashboard.html', 
                           total_flights=total_flights, 
                           total_users=total_users, 
                           total_bookings=total_bookings,
                           this_month_sales=this_month_sales)

# --- Manajemen Penerbangan ---
@app.route('/admin/flights')
@admin_required
def admin_flights():
    flights = list(flights_collection.find().sort('departure_time', 1))
    return render_template('admin_flights.html', flights=flights)

@app.route('/admin/flights/add', methods=['GET', 'POST'])
@admin_required
def admin_add_flight():
    if request.method == 'POST':
        try:
            flight_data = {
                'flight_number': request.form['flight_number'].upper(),
                'origin_airport': request.form['origin_airport'].upper(),
                'destination_airport': request.form['destination_airport'].upper(),
                'departure_time': datetime.strptime(request.form['departure_time'], '%Y-%m-%dT%H:%M'),
                'arrival_time': datetime.strptime(request.form['arrival_time'], '%Y-%m-%dT%H:%M'),
                'airline': request.form['airline'],
                'total_seats': int(request.form['total_seats']),
                'price': float(request.form['price'])
            }
            flight_data['available_seats'] = flight_data['total_seats']
            flights_collection.insert_one(flight_data)
            flash('Penerbangan berhasil ditambahkan!', 'success')
            return redirect(url_for('admin_flights'))
        except Exception as e:
            flash(f'Gagal menambahkan penerbangan: {e}', 'error')
    return render_template('admin_add_flight.html')

@app.route('/admin/flights/edit/<flight_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_flight(flight_id):
    flight = flights_collection.find_one({'_id': ObjectId(flight_id)})
    if not flight:
        flash('Penerbangan tidak ditemukan.', 'error')
        return redirect(url_for('admin_flights'))

    if request.method == 'POST':
        try:
            updated_data = {
                'flight_number': request.form['flight_number'].upper(),
                'origin_airport': request.form['origin_airport'].upper(),
                'destination_airport': request.form['destination_airport'].upper(),
                'departure_time': datetime.strptime(request.form['departure_time'], '%Y-%m-%dT%H:%M'),
                'arrival_time': datetime.strptime(request.form['arrival_time'], '%Y-%m-%dT%H:%M'),
                'airline': request.form['airline'],
                'total_seats': int(request.form['total_seats']),
                'price': float(request.form['price'])
            }
            flights_collection.update_one({'_id': ObjectId(flight_id)}, {'$set': updated_data})
            flash('Data penerbangan berhasil diperbarui.', 'success')
            return redirect(url_for('admin_flights'))
        except Exception as e:
            flash(f'Gagal memperbarui data: {e}', 'error')
    
    flight['departure_time_str'] = flight['departure_time'].strftime('%Y-%m-%dT%H:%M')
    flight['arrival_time_str'] = flight['arrival_time'].strftime('%Y-%m-%dT%H:%M')
    return render_template('admin_edit_flight.html', flight=flight)

@app.route('/admin/flights/delete/<flight_id>', methods=['POST'])
@admin_required
def admin_delete_flight(flight_id):
    flights_collection.delete_one({'_id': ObjectId(flight_id)})
    bookings_collection.delete_many({'flight_id': ObjectId(flight_id)})
    flash('Penerbangan berhasil dihapus.', 'success')
    return redirect(url_for('admin_flights'))

# --- Manajemen Pengguna ---
@app.route('/admin/users')
@admin_required
def admin_users():
    users = list(users_collection.find())
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/edit/<user_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(user_id):
    user = users_collection.find_one({'_id': ObjectId(user_id)})
    if not user:
        flash('Pengguna tidak ditemukan.', 'error')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        updated_data = {
            'name': request.form['name'],
            'username': request.form['username'],
            'email': request.form['email'],
            'role': request.form['role']
        }
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': updated_data})
        flash('Data pengguna berhasil diperbarui.', 'success')
        return redirect(url_for('admin_users'))
        
    return render_template('admin_edit_user.html', user=user)

@app.route('/admin/users/delete/<user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    users_collection.delete_one({'_id': ObjectId(user_id)})
    bookings_collection.delete_many({'user_id': ObjectId(user_id)})
    flash('Pengguna berhasil dihapus.', 'success')
    return redirect(url_for('admin_users'))

# --- Manajemen Pemesanan ---
@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    all_bookings = list(bookings_collection.find().sort('booking_date', -1))
    # Anda bisa menambahkan join/lookup data user dan flight di sini jika perlu
    return render_template('admin_bookings.html', bookings=all_bookings)

# =======================================================================
# MENJALANKAN APLIKASI
# =======================================================================
if __name__ == '__main__':
    app.run(debug=True)