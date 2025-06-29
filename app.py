from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import bcrypt
from datetime import datetime, timedelta
from functools import wraps # Import wraps untuk decorator

app = Flask(__name__)
# Ganti dengan kunci rahasia yang kuat untuk sesi Flask Anda!
# Ini penting untuk keamanan. Anda bisa menghasilkan string acak yang panjang.
app.secret_key = 'super_secret_key_yang_sangat_kuat_dan_panjang_ini_untuk_admin_panel_penerbangan' 

# Inisialisasi koneksi MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['flight_booking_db'] # Nama database Anda

# Definisikan koleksi-koleksi MongoDB
users_collection = db['users']
flights_collection = db['flights']
bookings_collection = db['bookings']

# --- Fungsi Helper ---

# Fungsi untuk menghash password sebelum disimpan ke database
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Fungsi untuk memverifikasi password
def check_password(hashed_password, password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# --- Decorator untuk Memastikan Pengguna adalah Admin ---
# Ini akan digunakan di atas setiap rute admin untuk memproteksinya
def admin_required(f):
    @wraps(f) # Penting untuk menjaga nama fungsi dan dokumentasi
    def wrap(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Anda tidak memiliki izin untuk mengakses halaman ini.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

# --- Rute-rute Aplikasi Umum ---

# Rute Halaman Utama (Beranda)
@app.route('/')
def index():
    # Ambil waktu saat ini
    now = datetime.now()
    
    # Query untuk mencari penerbangan yang akan datang dan masih tersedia
    query = {
        'departure_time': {'$gt': now},
        'available_seats': {'$gt': 0}
    }
    
    # Ambil 10 penerbangan terdekat yang tersedia
    available_flights = list(flights_collection.find(query).sort('departure_time', 1).limit(10))
    
    # Kirim data penerbangan ke template
    return render_template('index.html', available_flights=available_flights)

# Rute Registrasi Pengguna
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        name = request.form['name']

        # Validasi: Cek apakah username atau email sudah terdaftar
        if users_collection.find_one({'$or': [{'username': username}, {'email': email}]}):
            flash('Username atau Email sudah terdaftar!', 'error')
            return redirect(url_for('register'))

        # Hash password sebelum disimpan
        hashed_pass = hash_password(password)
        # Default role untuk pengguna baru adalah 'user'
        users_collection.insert_one({
            'username': username,
            'password': hashed_pass,
            'email': email,
            'name': name,
            'role': 'user', # Default role
            'created_at': datetime.now()
        })
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    # Jika GET request, tampilkan form registrasi
    return render_template('register.html')

# Rute Login Pengguna (Modifikasi untuk Pengalihan Role dan Hardcoded Admin)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # --- Logika Hardcoded Admin ---
        if username == "admin" and password == "admin123":
            session['user_id'] = "admin_hardcoded_id" # ID placeholder untuk admin
            session['username'] = "admin"
            session['role'] = "admin"
            flash('Selamat datang Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        # --- Akhir Logika Hardcoded Admin ---
        
        # Jika bukan admin hardcoded, lakukan login seperti biasa dari database
        user = users_collection.find_one({'username': username})
        if user and check_password(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user.get('role', 'user') # Ambil peran, default 'user'

            flash('Login berhasil!', 'success')
            return redirect(url_for('index')) # Redirect ke dashboard pengguna (halaman utama)
        else:
            flash('Username atau password salah', 'error')
    return render_template('login.html')

# Rute Logout Pengguna
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None) # Hapus juga role dari sesi
    flash('Anda telah logout.', 'info')
    return redirect(url_for('index'))

# Rute untuk Halaman Form Pencarian Tiket (Baru Dipisahkan)
@app.route('/cari_jadwal')
def cari_jadwal():
    return render_template('cari_jadwal.html')

# Rute Pencarian Penerbangan berdasarkan kriteria
@app.route('/search_flights', methods=['GET'])
def search_flights():
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    departure_date_str = request.args.get('departure_date')

    # Validasi input pencarian
    if not origin or not destination or not departure_date_str:
        flash('Harap lengkapi asal, tujuan, dan tanggal keberangkatan.', 'warning')
        return redirect(url_for('cari_jadwal')) # Redirect ke halaman cari_jadwal jika input kurang

    try:
        # Konversi tanggal string dari form ke objek datetime
        departure_date = datetime.strptime(departure_date_str, '%Y-%m-%d')
        # Buat rentang waktu untuk mencari penerbangan di seluruh hari itu
        end_of_day = departure_date + timedelta(days=1)
    except ValueError:
        flash('Format tanggal tidak valid. Gunakan YYYY-MM-DD.', 'error')
        return redirect(url_for('cari_jadwal')) # Redirect ke halaman cari_jadwal jika format tanggal salah

    # Query MongoDB untuk mencari penerbangan
    query = {
        'origin_airport': origin.upper(),        # Konversi ke uppercase untuk konsistensi
        'destination_airport': destination.upper(), # Konversi ke uppercase untuk konsistensi
        'departure_time': {
            '$gte': departure_date, # Greater than or equal to start of day
            '$lt': end_of_day       # Less than end of day (next day's start)
        },
        'available_seats': {'$gt': 0} # Hanya tampilkan penerbangan dengan kursi tersedia
    }
    flights = list(flights_collection.find(query).sort('departure_time', 1))
    # Render template search.html dengan hasil penerbangan
    return render_template('search.html', flights=flights)

# Rute untuk melihat semua jadwal penerbangan yang tersedia (untuk user biasa)
@app.route('/all_flights')
def all_flights():
    flights = list(flights_collection.find().sort('departure_time', 1))
    return render_template('all_flights.html', flights=flights)

# Rute untuk Detail Penerbangan dan Form Pemesanan
@app.route('/book_flight/<flight_id>', methods=['GET', 'POST'])
def book_flight(flight_id):
    if 'user_id' not in session:
        flash('Silakan login untuk memesan penerbangan.', 'info')
        return redirect(url_for('login'))

    flight = flights_collection.find_one({'_id': ObjectId(flight_id)})
    if not flight:
        flash('Penerbangan tidak ditemukan.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            num_tickets = int(request.form['num_tickets'])
        except ValueError:
            flash('Jumlah tiket harus berupa angka valid.', 'error')
            return redirect(request.url)

        if num_tickets <= 0:
            flash('Jumlah tiket minimal 1.', 'error')
            return redirect(request.url)

        passengers_data = []
        for i in range(num_tickets):
            passenger_name = request.form.get(f'passenger_name_{i+1}')
            passenger_id_num = request.form.get(f'passenger_id_number_{i+1}')
            if not passenger_name or not passenger_id_num:
                flash(f'Harap lengkapi detail penumpang untuk penumpang {i+1}.', 'error')
                return redirect(request.url)

            passengers_data.append({
                'name': passenger_name,
                'id_number': passenger_id_num
            })

        if num_tickets > flight['available_seats']:
            flash(f'Kursi tidak mencukupi. Hanya {flight["available_seats"]} kursi tersisa.', 'error')
            return redirect(request.url)

        total_price = num_tickets * flight['price']

        try:
            updated_flight = flights_collection.find_one_and_update(
                {'_id': ObjectId(flight_id), 'available_seats': {'$gte': num_tickets}},
                {'$inc': {'available_seats': -num_tickets}},
                return_document=True
            )

            if updated_flight:
                bookings_collection.insert_one({
                    'user_id': ObjectId(session['user_id']) if session['user_id'] != "admin_hardcoded_id" else None, # ID user untuk booking (None jika admin hardcoded)
                    'flight_id': ObjectId(flight_id),
                    'booking_date': datetime.now(),
                    'number_of_tickets': num_tickets,
                    'total_price': total_price,
                    'passengers': passengers_data,
                    'status': 'confirmed'
                })
                flash('Pemesanan penerbangan berhasil!', 'success')
                return redirect(url_for('booking_history'))
            else:
                flash('Gagal memesan penerbangan. Kursi tidak mencukupi atau terjadi pemesanan bersamaan.', 'error')
                return redirect(request.url)

        except Exception as e:
            flash(f'Terjadi kesalahan: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('booking.html', flight=flight)

# Rute Riwayat Pemesanan Pengguna
@app.route('/booking_history')
def booking_history():
    # Admin hardcoded tidak akan punya riwayat booking di DB, jadi handle khusus
    if session.get('user_id') == "admin_hardcoded_id":
        flash('Admin tidak memiliki riwayat pemesanan pribadi.', 'info')
        return redirect(url_for('admin_dashboard'))
        
    if 'user_id' not in session:
        flash('Silakan login untuk melihat riwayat pemesanan Anda.', 'info')
        return redirect(url_for('login'))

    user_bookings = list(bookings_collection.find({'user_id': ObjectId(session['user_id'])}).sort('booking_date', -1))

    detailed_bookings = []
    for booking in user_bookings:
        flight = flights_collection.find_one({'_id': booking['flight_id']})
        booking_data = dict(booking) 
        if flight:
            booking_data['flight_details'] = flight
        else:
            booking_data['flight_details'] = {
                'flight_number': 'N/A',
                'origin_airport': 'N/A',
                'destination_airport': 'N/A',
                'departure_time': datetime.min,
                'airline': 'N/A'
            }
        detailed_bookings.append(booking_data)
    
    return render_template('history.html', bookings=detailed_bookings)

# --- Rute-rute Admin Panel ---

# 1. Dashboard Admin
@app.route('/admin_dashboard')
@admin_required 
def admin_dashboard():
    # Data tracking yang sudah ada
    total_flights = flights_collection.count_documents({})
    total_users = users_collection.count_documents({})
    total_bookings = bookings_collection.count_documents({})
    
    # --- Data tracking baru untuk metrik dashboard ---
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    last_week = today - timedelta(weeks=1)
    last_quarter_start = datetime(today.year, (today.month - 1) // 3 * 3 + 1, 1)

    # Today's Money (Total pendapatan hari ini)
    today_bookings_pipeline = [
        {"$match": {"booking_date": {"$gte": today}}},
        {"$group": {"_id": None, "total_price": {"$sum": "$total_price"}}}
    ]
    today_money_result = list(bookings_collection.aggregate(today_bookings_pipeline))
    today_money = today_money_result[0]['total_price'] if today_money_result else 0

    # Sales this month (Total pendapatan bulan ini)
    this_month_start = today.replace(day=1)
    this_month_bookings_pipeline = [
        {"$match": {"booking_date": {"$gte": this_month_start}}},
        {"$group": {"_id": None, "total_price": {"$sum": "$total_price"}}}
    ]
    this_month_sales_result = list(bookings_collection.aggregate(this_month_bookings_pipeline))
    this_month_sales = this_month_sales_result[0]['total_price'] if this_month_sales_result else 0
    
    # New Users this week (Pengguna baru minggu ini)
    new_users_week = users_collection.count_documents({'created_at': {'$gte': last_week}})

    # New Clients last quarter (Pengguna baru kuartal ini)
    new_clients_quarter = users_collection.count_documents({'created_at': {'$gte': last_quarter_start}})

    # Contoh data untuk laporan (top 5 flights by tickets booked)
    top_flights_pipeline = [
        {"$group": {"_id": "$flight_id", "count": {"$sum": "$number_of_tickets"}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_flights_raw = list(bookings_collection.aggregate(top_flights_pipeline))
    top_flights = []
    for item in top_flights_raw:
        flight_info = flights_collection.find_one({"_id": item["_id"]})
        if flight_info:
            top_flights.append({
                "flight_number": flight_info.get("flight_number", "N/A"),
                "airline": flight_info.get("airline", "N/A"),
                "origin": flight_info.get("origin_airport", "N/A"),
                "destination": flight_info.get("destination_airport", "N/A"),
                "tickets_booked": item["count"]
            })

    return render_template('admin_dashboard.html', 
                           total_flights=total_flights, 
                           total_users=total_users, 
                           total_bookings=total_bookings,
                           today_money=today_money,
                           this_month_sales=this_month_sales,
                           new_users_week=new_users_week,
                           new_clients_quarter=new_clients_quarter,
                           top_flights=top_flights)

@app.route('/')
def index():
    # --- PENAMBAHAN KODE ---
    # Ambil waktu saat ini
    now = datetime.now()
    
    # Query untuk mencari penerbangan yang akan datang dan masih tersedia
    query = {
        'departure_time': {'$gt': now},
        'available_seats': {'$gt': 0}
    }
    
    # Ambil 10 penerbangan terdekat yang tersedia
    available_flights = list(flights_collection.find(query).sort('departure_time', 1).limit(10))
    # --- AKHIR PENAMBAHAN KODE ---
    
    # Kirim data penerbangan ke template
    return render_template('index.html', available_flights=available_flights)

# 2. Manajemen Penerbangan
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
            flight_number = request.form['flight_number'].upper()
            origin_airport = request.form['origin_airport'].upper()
            destination_airport = request.form['destination_airport'].upper()
            departure_time_str = request.form['departure_time']
            arrival_time_str = request.form['arrival_time']
            airline = request.form['airline']
            total_seats = int(request.form['total_seats'])
            price = float(request.form['price'])

            # Konversi string tanggal/waktu ke objek datetime
            departure_time = datetime.strptime(departure_time_str, '%Y-%m-%dT%H:%M')
            arrival_time = datetime.strptime(arrival_time_str, '%Y-%m-%dT%H:%M')

            # Validasi dasar input
            if not all([flight_number, origin_airport, destination_airport, airline]) or \
               total_seats <= 0 or price <= 0 or departure_time >= arrival_time:
                flash('Input tidak valid. Pastikan semua field terisi, kursi/harga > 0, dan waktu keberangkatan < waktu kedatangan.', 'error')
                return redirect(url_for('admin_add_flight'))
            
            # Cek duplikasi nomor penerbangan
            if flights_collection.find_one({'flight_number': flight_number}):
                flash('Nomor penerbangan sudah ada.', 'error')
                return redirect(url_for('admin_add_flight'))

            flights_collection.insert_one({
                'flight_number': flight_number,
                'origin_airport': origin_airport,
                'destination_airport': destination_airport,
                'departure_time': departure_time,
                'arrival_time': arrival_time,
                'airline': airline,
                'total_seats': total_seats,
                'available_seats': total_seats, # Saat baru ditambahkan, available_seats = total_seats
                'price': price
            })
            flash('Penerbangan berhasil ditambahkan!', 'success')
            return redirect(url_for('admin_flights'))
        except ValueError:
            flash('Format input tidak valid (misal: tanggal/waktu atau angka tidak benar).', 'error')
        except Exception as e:
            flash(f'Terjadi kesalahan saat menambahkan penerbangan: {str(e)}', 'error')
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
            # Ambil data dari form
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

            # Hitung selisih kursi yang berubah
            # available_seats tidak boleh lebih dari total_seats
            # available_seats harus disesuaikan jika total_seats berubah
            old_total_seats = flight.get('total_seats', 0)
            old_available_seats = flight.get('available_seats', 0)
            new_total_seats = updated_data['total_seats']

            # Jika total_seats bertambah, kursi tersedia bertambah sejumlah selisihnya,
            # tetapi tidak boleh melebihi total_seats baru
            if new_total_seats > old_total_seats:
                updated_data['available_seats'] = min(old_available_seats + (new_total_seats - old_total_seats), new_total_seats)
            # Jika total_seats berkurang, kursi tersedia juga harus berkurang,
            # dan tidak boleh melebihi total_seats baru
            elif new_total_seats < old_total_seats:
                updated_data['available_seats'] = min(old_available_seats, new_total_seats)
            # Jika total_seats sama, available_seats tetap seperti sebelumnya
            else:
                updated_data['available_seats'] = old_available_seats
            
            # Validasi dasar input
            if not all([updated_data['flight_number'], updated_data['origin_airport'], 
                        updated_data['destination_airport'], updated_data['airline']]) or \
               updated_data['total_seats'] <= 0 or updated_data['price'] <= 0 or \
               updated_data['departure_time'] >= updated_data['arrival_time']:
                flash('Input tidak valid. Pastikan semua field terisi, kursi/harga > 0, dan waktu keberangkatan < waktu kedatangan.', 'error')
                return redirect(url_for('admin_edit_flight', flight_id=flight_id))
            
            # Cek duplikasi nomor penerbangan, kecuali untuk penerbangan itu sendiri
            existing_flight_with_number = flights_collection.find_one({'flight_number': updated_data['flight_number']})
            if existing_flight_with_number and existing_flight_with_number['_id'] != ObjectId(flight_id):
                flash('Nomor penerbangan sudah digunakan oleh penerbangan lain.', 'error')
                return redirect(url_for('admin_edit_flight', flight_id=flight_id))

            flights_collection.update_one({'_id': ObjectId(flight_id)}, {'$set': updated_data})
            flash('Penerbangan berhasil diperbarui!', 'success')
            return redirect(url_for('admin_flights'))
        except ValueError:
            flash('Format input tidak valid (misal: tanggal/waktu atau angka tidak benar).', 'error')
        except Exception as e:
            flash(f'Terjadi kesalahan saat memperbarui penerbangan: {str(e)}', 'error')
    
    # Format tanggal dan waktu untuk tampilan di form HTML
    if flight['departure_time']:
        flight['departure_time_str'] = flight['departure_time'].strftime('%Y-%m-%dT%H:%M')
    if flight['arrival_time']:
        flight['arrival_time_str'] = flight['arrival_time'].strftime('%Y-%m-%dT%H:%M')

    return render_template('admin_edit_flight.html', flight=flight)

@app.route('/admin/flights/delete/<flight_id>', methods=['POST'])
@admin_required
def admin_delete_flight(flight_id):
    # Optional: Tambahkan konfirmasi di frontend atau cek apakah ada booking terkait
    # Jika ada booking terkait, mungkin lebih baik menonaktifkan penerbangan daripada menghapusnya
    
    # Hapus juga booking yang terkait dengan penerbangan ini jika diperlukan
    bookings_collection.delete_many({'flight_id': ObjectId(flight_id)})
    
    result = flights_collection.delete_one({'_id': ObjectId(flight_id)})
    if result.deleted_count:
        flash('Penerbangan dan semua pemesanan terkait berhasil dihapus!', 'success')
    else:
        flash('Penerbangan tidak ditemukan.', 'error')
    return redirect(url_for('admin_flights'))

# 3. Manajemen Pengguna
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
        try:
            updated_data = {
                'username': request.form['username'],
                'email': request.form['email'],
                'name': request.form['name'],
                'role': request.form['role'] # Admin bisa mengubah role
            }

            # Jika password diisi, update password
            new_password = request.form['password']
            if new_password:
                updated_data['password'] = hash_password(new_password)
            
            # Cek duplikasi username/email, kecuali untuk user itu sendiri
            existing_user = users_collection.find_one({'$or': [
                {'username': updated_data['username']},
                {'email': updated_data['email']}
            ]})
            if existing_user and existing_user['_id'] != ObjectId(user_id):
                flash('Username atau Email sudah digunakan oleh pengguna lain.', 'error')
                return redirect(url_for('admin_edit_user', user_id=user_id))

            users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': updated_data})
            flash('Informasi pengguna berhasil diperbarui!', 'success')
            return redirect(url_for('admin_users'))
        except Exception as e:
            flash(f'Terjadi kesalahan saat memperbarui pengguna: {str(e)}', 'error')
    
    return render_template('admin_edit_user.html', user=user)

@app.route('/admin/users/delete/<user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    # Optional: Tambahkan konfirmasi di frontend

    # Hapus semua booking yang terkait dengan user ini
    bookings_collection.delete_many({'user_id': ObjectId(user_id)})

    result = users_collection.delete_one({'_id': ObjectId(user_id)})
    if result.deleted_count:
        flash('Pengguna dan semua pemesanan terkait berhasil dihapus!', 'success')
    else:
        flash('Pengguna tidak ditemukan.', 'error')
    return redirect(url_for('admin_users'))

# 4. Manajemen Pemesanan
@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    # Mengambil semua pemesanan dan melakukan lookup ke flights dan users
    pipeline = [
        {
            '$lookup': {
                'from': 'flights',
                'localField': 'flight_id',
                'foreignField': '_id',
                'as': 'flight_details'
            }
        },
        {
            '$unwind': {
                'path': '$flight_details',
                'preserveNullAndEmptyArrays': True # Penting jika flight_id tidak ditemukan
            }
        },
        {
            '$lookup': {
                'from': 'users',
                'localField': 'user_id',
                'foreignField': '_id',
                'as': 'user_details'
            }
        },
        {
            '$unwind': {
                'path': '$user_details',
                'preserveNullAndEmptyArrays': True # Penting jika user_id tidak ditemukan
            }
        },
        {
            '$sort': {'booking_date': -1} # Urutkan dari yang terbaru
        }
    ]
    bookings = list(bookings_collection.aggregate(pipeline))
    return render_template('admin_bookings.html', bookings=bookings)

# 5. Rute untuk Laporan (sudah ada di admin_dashboard sebagai contoh sederhana)
# Jika ingin laporan lebih kompleks, bisa buat rute terpisah seperti /admin/reports/sales

# Jalankan aplikasi Flask
if __name__ == '__main__':
    app.run(debug=True)